/**
 * Renders the edit to an MP4, entirely in the browser.
 *
 * The source file is read where it sits on the user's computer; nothing is
 * uploaded. Mediabunny handles the container (reading and writing MP4) and
 * drives the browser's own video and audio encoders, which on most PCs means
 * the graphics card does the heavy lifting.
 *
 * Only the kept stretches are decoded. Each frame is drawn by the same
 * drawFrame() the preview uses, then re-timed so the removed stretches close
 * up with no gap.
 */

import { FORMATS, drawFrame } from './renderer.js';
import { keptRanges, outputDuration } from './project.js';

// Pinned to an exact release. Loaded on first export, not on page load, so
// opening the editor stays fast.
export const MEDIABUNNY_URL =
  'https://cdn.jsdelivr.net/npm/mediabunny@1.61.6/dist/bundles/mediabunny.min.mjs';

let mediabunny = null;

export async function loadMediabunny() {
  if (!mediabunny) {
    mediabunny = import(MEDIABUNNY_URL).catch((error) => {
      mediabunny = null; // let a later attempt retry, e.g. after a network blip
      throw new Error(
        `Could not load the video engine (${error.message}). Check the internet ` +
        'connection; if the office network blocks cdn.jsdelivr.net, ask IT to allow it.',
      );
    });
  }
  return mediabunny;
}

// Preferred first. H.264 and AAC are what every social platform accepts; the
// others are fallbacks for browsers without those encoders.
const VIDEO_PREFERENCE = ['avc', 'hevc', 'vp9', 'av1'];
const AUDIO_PREFERENCE = ['aac', 'opus'];

const OUTPUT_FRAME_RATE = 30;

/** Copy samples [from, to) of an AudioBuffer into a new one. */
function sliceAudioBuffer(buffer, from, to) {
  const piece = new AudioBuffer({
    length: to - from,
    numberOfChannels: buffer.numberOfChannels,
    sampleRate: buffer.sampleRate,
  });
  for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {
    piece.copyToChannel(buffer.getChannelData(channel).subarray(from, to), channel);
  }
  return piece;
}

/** Choose the best audio codec this browser can encode, resampling if needed. */
async function chooseAudio(mb, format, audioTrack) {
  const supported = format.getSupportedAudioCodecs();
  const codecs = AUDIO_PREFERENCE.filter((codec) => supported.includes(codec));
  const numberOfChannels = Math.min(2, audioTrack.numberOfChannels || 2);

  // First at the source's own rate; then at 48 kHz, which every encoder
  // accepts. Phone video is usually 44.1 kHz, and some encoders (Opus) refuse
  // it -- without this fallback the export would silently lose its sound.
  for (const sampleRate of [audioTrack.sampleRate, 48000]) {
    const codec = await mb.getFirstEncodableAudioCodec(codecs, { numberOfChannels, sampleRate });
    if (codec) return { codec, numberOfChannels, sampleRate };
  }
  return null;
}

/**
 * Export the edit.
 *
 * @param project   the edit (project.js)
 * @param assets    fonts and logos (renderer.loadAssets)
 * @param options   { onProgress(fraction, message), signal, overlays }
 * @returns         { blob, videoCodec, audioCodec, duration, warnings }
 */
export async function exportVideo(project, assets, { onProgress = () => {}, signal, overlays } = {}) {
  const mb = await loadMediabunny();
  const { width, height } = FORMATS[project.format];
  const ranges = keptRanges(project);
  const total = outputDuration(project);
  const warnings = [];

  if (!ranges.length || total <= 0) {
    throw new Error('Nothing is left to export: the whole video has been trimmed or removed.');
  }

  const input = new mb.Input({ formats: mb.ALL_FORMATS, source: new mb.BlobSource(project.file) });
  let output = null;

  try {
    onProgress(0, 'Reading the video');
    const videoTrack = await input.getPrimaryVideoTrack();
    if (!videoTrack) throw new Error('This file has no video in it.');
    if (!(await videoTrack.canDecode())) {
      throw new Error(
        `This browser cannot read this video's format (${videoTrack.codec || 'unknown'}). ` +
        'Try current Chrome or Edge, or convert the file to a standard MP4 first.',
      );
    }

    let audioTrack = await input.getPrimaryAudioTrack();
    if (audioTrack && !(await audioTrack.canDecode())) {
      warnings.push("The sound in this file couldn't be read, so the export is silent.");
      audioTrack = null;
    }

    const format = new mb.Mp4OutputFormat();
    output = new mb.Output({ format, target: new mb.BufferTarget() });

    const videoCodecs = VIDEO_PREFERENCE.filter((codec) => format.getSupportedVideoCodecs().includes(codec));
    const videoCodec = await mb.getFirstEncodableVideoCodec(videoCodecs, { width, height });
    if (!videoCodec) {
      throw new Error("This browser can't encode video. Use current Chrome or Edge.");
    }
    if (videoCodec !== 'avc') {
      warnings.push(
        `Exported as ${videoCodec.toUpperCase()} because this browser has no H.264 encoder. ` +
        'Some social platforms may reject it; Chrome or Edge on Windows or Mac exports H.264.',
      );
    }

    const frameCanvas = new OffscreenCanvas(width, height);
    const ctx = frameCanvas.getContext('2d', { alpha: false });
    const videoSource = new mb.CanvasSource(frameCanvas, { codec: videoCodec, bitrate: mb.QUALITY_HIGH });
    output.addVideoTrack(videoSource, { frameRate: OUTPUT_FRAME_RATE });

    let audioSource = null;
    let audioCodec = null;
    if (audioTrack) {
      const audio = await chooseAudio(mb, format, audioTrack);
      if (audio) {
        audioCodec = audio.codec;
        audioSource = new mb.AudioBufferSource({
          codec: audio.codec,
          bitrate: mb.QUALITY_HIGH,
          transform: { sampleRate: audio.sampleRate, numberOfChannels: audio.numberOfChannels },
        });
        output.addAudioTrack(audioSource);
        if (audio.codec !== 'aac') {
          warnings.push(
            `Sound exported as ${audio.codec.toUpperCase()} because this browser has no AAC encoder. ` +
            'Chrome or Edge on Windows or Mac exports AAC.',
          );
        }
      } else {
        warnings.push("This browser can't encode sound, so the export is silent.");
      }
    }

    await output.start();

    // Video and audio run side by side so the file is written interleaved and
    // each side waits for the encoder when it falls behind (backpressure).
    const renderVideo = async () => {
      const sink = new mb.CanvasSink(videoTrack, { poolSize: 2 });
      let base = 0;
      for (const range of ranges) {
        for await (const frame of sink.canvases(range.start, range.end)) {
          signal?.throwIfAborted();
          const start = Math.max(frame.timestamp, range.start);
          const end = Math.min(frame.timestamp + frame.duration, range.end);
          if (end - start <= 0.0005) continue;

          const outputTime = base + (start - range.start);
          drawFrame(
            ctx, frame.canvas, frame.canvas.width, frame.canvas.height,
            { source: start, output: outputTime }, project, assets, overlays,
          );
          await videoSource.add(outputTime, end - start);
          onProgress(Math.min(0.99, (outputTime + (end - start)) / total), 'Rendering');
        }
        base += range.end - range.start;
      }
      videoSource.close();
    };

    const renderAudio = async () => {
      if (!audioSource) return;
      const sink = new mb.AudioBufferSink(audioTrack);
      for (const range of ranges) {
        for await (const { buffer, timestamp } of sink.buffers(range.start, range.end)) {
          signal?.throwIfAborted();
          const rate = buffer.sampleRate;
          const from = Math.max(0, Math.round((range.start - timestamp) * rate));
          const to = Math.min(buffer.length, Math.round((range.end - timestamp) * rate));
          if (to <= from) continue;
          const piece = from === 0 && to === buffer.length ? buffer : sliceAudioBuffer(buffer, from, to);
          // Each buffer is placed directly after the previous one, so the
          // removed stretches close up without a gap.
          await audioSource.add(piece);
        }
      }
      audioSource.close();
    };

    await Promise.all([renderVideo(), renderAudio()]);

    onProgress(0.995, 'Finishing the file');
    await output.finalize();

    const blob = new Blob([output.target.buffer], { type: format.mimeType });
    onProgress(1, 'Done');
    return { blob, videoCodec, audioCodec, duration: total, warnings };
  } catch (error) {
    if (output && output.state !== 'finalized' && output.state !== 'canceled') {
      await output.cancel().catch(() => {});
    }
    throw error;
  } finally {
    input.dispose();
  }
}
