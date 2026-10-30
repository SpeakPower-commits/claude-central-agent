/**
 * SpeakPower Studio -- the editor page.
 *
 * Everything happens in this browser tab. The video is opened from the user's
 * computer, previewed through a <video> element drawn onto a canvas, and
 * exported by exporter.js. No part of the video is sent anywhere.
 */

import {
  addCut, createProject, formatTime, keptRanges, nextPlayableTime,
  outputDuration, removeCut, setTrim, sourceToOutput,
} from './project.js';
import { FORMATS, drawFrame, loadAssets } from './renderer.js';
import { Timeline } from './timeline.js';
import { exportVideo, loadMediabunny } from './exporter.js';
import { editSegmentText, replaceEverywhere, segmentsFromSrt } from './captions.js';
import { transcribeFile } from './speech.js';

// Preview runs at a reduced resolution so it stays smooth on modest PCs. The
// renderer lays everything out proportionally, so this is a faithful scale
// model of the full-size export.
const PREVIEW_MAX_SIDE = 960;
// Below this, a jump in playback is just a decoder rounding error, not a cut.
const SKIP_TOLERANCE = 0.04;

const $ = (selector) => document.querySelector(selector);

const ui = {
  drop: $('#drop'),
  file: $('#file'),
  viewer: $('#viewer'),
  previewFrame: $('#preview-frame'),
  preview: $('#preview'),
  play: $('#play'),
  clockNow: $('#clock-now'),
  clockTotal: $('#clock-total'),
  clockNote: $('#clock-note'),
  remove: $('#remove'),
  cuts: $('#cuts'),
  formats: $('#formats'),
  headline: $('#headline'),
  logo: $('#logo'),
  exportButton: $('#export'),
  progress: $('#progress'),
  progressFill: $('#progress-fill'),
  progressText: $('#progress-text'),
  cancel: $('#cancel'),
  result: $('#result'),
  status: $('#status'),
  unsupported: $('#unsupported'),
  captionsOn: $('#captions-on'),
  captionModel: $('#caption-model'),
  captionLanguage: $('#caption-language'),
  autoCaptions: $('#auto-captions'),
  captionProgress: $('#caption-progress'),
  captionProgressFill: $('#caption-progress-fill'),
  captionProgressText: $('#caption-progress-text'),
  captionCancel: $('#caption-cancel'),
  srt: $('#srt'),
  transcript: $('#transcript'),
  lines: $('#lines'),
  captionCount: $('#caption-count'),
  replaceForm: $('#replace-form'),
  replaceFind: $('#replace-find'),
  replaceWith: $('#replace-with'),
};

const state = {
  project: null,
  video: null,
  videoUrl: null,
  assets: { logos: {} },
  selection: null,
  exporting: null,       // AbortController while an export runs
  captioning: null,      // AbortController while captions are being made
  resultUrl: null,
  currentLine: -1,
};

const previewCtx = ui.preview.getContext('2d', { alpha: false });

// --- Messages ----------------------------------------------------------------

function showStatus(message, kind = 'info') {
  ui.status.hidden = !message;
  ui.status.textContent = message || '';
  ui.status.className = `notice notice-${kind}`;
}

// --- Support check -----------------------------------------------------------

function browserSupported() {
  return typeof VideoEncoder !== 'undefined'
    && typeof VideoDecoder !== 'undefined'
    && typeof OffscreenCanvas !== 'undefined'
    && typeof AudioBuffer !== 'undefined';
}

// --- Format choices ----------------------------------------------------------

function buildFormatChoices() {
  ui.formats.replaceChildren(...Object.entries(FORMATS).map(([key, format], index) => {
    const label = document.createElement('label');
    label.className = 'choice';
    label.innerHTML = `
      <input type="radio" name="format" value="${key}" ${index === 0 ? 'checked' : ''} />
      <span><strong>${format.label}</strong><small>${format.use}</small></span>`;
    return label;
  }));
}

function sizePreviewCanvas() {
  const project = state.project;
  const { width, height } = FORMATS[project ? project.format : '9:16'];
  const scale = PREVIEW_MAX_SIDE / Math.max(width, height);
  ui.preview.width = Math.round(width * scale);
  ui.preview.height = Math.round(height * scale);
  ui.previewFrame.dataset.format = project ? project.format : '9:16';
}

// --- Rendering the preview ---------------------------------------------------

function drawPreview() {
  const { project, video } = state;
  if (!project || !video || video.readyState < 2) return;
  const time = video.currentTime;
  drawFrame(
    previewCtx, video, video.videoWidth, video.videoHeight,
    { source: time, output: sourceToOutput(project, time) },
    project, state.assets,
  );
}

function updateClock() {
  const { project, video } = state;
  if (!project || !video) return;
  ui.clockNow.textContent = formatTime(sourceToOutput(project, video.currentTime));
  ui.clockTotal.textContent = formatTime(outputDuration(project));
  const removed = project.duration - outputDuration(project);
  ui.clockNote.textContent = removed > 0.05
    ? `${formatTime(removed)} removed from ${formatTime(project.duration)}`
    : '';
}

function tick() {
  const { project, video } = state;
  if (project && video && !video.paused) {
    // Playback skips straight over trimmed and removed parts, so the preview
    // plays exactly what the export will contain.
    const next = nextPlayableTime(project, video.currentTime);
    if (next === null) {
      video.pause();
      video.currentTime = project.trim.start;
    } else if (next - video.currentTime > SKIP_TOLERANCE) {
      video.currentTime = next;
    }
  }
  if (video) {
    timeline.setPlayhead(video.currentTime);
    updateCurrentLine(video.currentTime);
  }
  drawPreview();
  updateClock();
  requestAnimationFrame(tick);
}

// --- The edit ----------------------------------------------------------------

function renderCuts() {
  const { project } = state;
  ui.cuts.replaceChildren(...(project?.cuts || []).map((cut, index) => {
    const item = document.createElement('li');
    item.innerHTML = `<span>Removed ${formatTime(cut.start)} – ${formatTime(cut.end)}
      <small>(${formatTime(cut.end - cut.start)})</small></span>`;
    const undo = document.createElement('button');
    undo.type = 'button';
    undo.className = 'button-link';
    undo.textContent = 'Put back';
    undo.addEventListener('click', () => {
      removeCut(project, index);
      editChanged();
    });
    item.append(undo);
    return item;
  }));
}

function editChanged() {
  timeline.render();
  renderCuts();
  markRemovedLines();
  updateClock();
  clearResult();
}

const timeline = new Timeline($('#timeline'), {
  onSeek: (time) => {
    if (!state.video) return;
    state.video.currentTime = time;
  },
  onTrim: (start, end) => {
    if (!state.project) return;
    if (setTrim(state.project, start, end)) {
      const video = state.video;
      // Keep the playhead inside the trim so the preview shows the new edge.
      if (video.currentTime < start || video.currentTime > end) video.currentTime = start;
      editChanged();
    }
  },
  onSelect: (range) => {
    state.selection = range;
    ui.remove.disabled = !range;
  },
});

ui.remove.addEventListener('click', () => {
  if (!state.project || !state.selection) return;
  if (addCut(state.project, state.selection.start, state.selection.end)) {
    timeline.setSelection(null);
    editChanged();
  }
});

// --- Captions ----------------------------------------------------------------

/** Index of the caption line playing at a time, or -1. */
function lineAt(segments, time) {
  let low = 0;
  let high = segments.length - 1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (time < segments[middle].start) high = middle - 1;
    else if (time >= segments[middle].end) low = middle + 1;
    else return middle;
  }
  return -1;
}

function isRemoved(project, segment) {
  const middle = (segment.start + segment.end) / 2;
  return nextPlayableTime(project, middle) !== middle;
}

function markRemovedLines() {
  const { project } = state;
  if (!project) return;
  [...ui.lines.children].forEach((item, index) => {
    const segment = project.captions.segments[index];
    if (segment) item.classList.toggle('is-removed', isRemoved(project, segment));
  });
}

function renderTranscript() {
  const { project } = state;
  const segments = project?.captions.segments || [];
  ui.transcript.hidden = !segments.length;
  ui.captionCount.textContent = segments.length ? `· ${segments.length} lines` : '';
  state.currentLine = -1;

  ui.lines.replaceChildren(...segments.map((segment, index) => {
    const item = document.createElement('li');
    const time = document.createElement('button');
    time.type = 'button';
    time.className = 'line-time';
    time.textContent = formatTime(segment.start);
    time.title = 'Jump here';
    time.addEventListener('click', () => {
      if (state.video) state.video.currentTime = segment.start + 0.01;
    });

    const text = document.createElement('input');
    text.className = 'line-text';
    text.value = segment.text;
    text.setAttribute('aria-label', `Caption at ${formatTime(segment.start)}`);
    // Update the data, not the list: rebuilding the list on every keystroke
    // would steal the cursor out of the box being typed in.
    text.addEventListener('input', () => {
      const next = project.captions.segments.slice();
      next[index] = editSegmentText(next[index], text.value);
      project.captions.segments = next;
      clearResult();
    });

    item.append(time, text);
    return item;
  }));
  markRemovedLines();
}

function updateCurrentLine(time) {
  const segments = state.project?.captions.segments;
  if (!segments?.length) return;
  const index = lineAt(segments, time);
  if (index === state.currentLine) return;
  ui.lines.children[state.currentLine]?.classList.remove('is-current');
  const item = ui.lines.children[index];
  if (item) {
    item.classList.add('is-current');
    // Follow playback without yanking the page around.
    if (!state.video.paused) item.scrollIntoView({ block: 'nearest' });
  }
  state.currentLine = index;
}

function setSegments(segments) {
  state.project.captions.segments = segments;
  renderTranscript();
  clearResult();
}

function setCaptioning(active) {
  ui.autoCaptions.disabled = active || !state.project;
  ui.autoCaptions.textContent = active ? 'Making captions…' : 'Auto captions';
  ui.captionProgress.hidden = !active;
}

ui.autoCaptions.addEventListener('click', async () => {
  const { project } = state;
  if (!project || state.captioning) return;
  if (project.captions.segments.length
      && !window.confirm('Replace the current captions, including any corrections you made?')) return;

  state.video?.pause();
  const controller = new AbortController();
  state.captioning = controller;
  setCaptioning(true);
  showStatus('');
  ui.captionProgressFill.style.width = '0%';

  const started = performance.now();
  try {
    const { segments, wordLevel } = await transcribeFile(project.file, {
      model: ui.captionModel.value,
      language: ui.captionLanguage.value,
      signal: controller.signal,
      onProgress: (stage, fraction) => {
        ui.captionProgressFill.style.width = `${Math.round(fraction * 100)}%`;
        ui.captionProgressText.textContent = `${stage} — ${Math.round(fraction * 100)}%`;
      },
    });
    if (state.project !== project) return; // the user opened another video meanwhile
    if (!segments.length) {
      showStatus('No speech was found in this video.', 'warn');
      return;
    }
    setSegments(segments);
    const seconds = Math.round((performance.now() - started) / 1000);
    showStatus(
      `${segments.length} caption lines made in ${seconds}s. Check them below — fix any word by typing, ` +
      'or use Replace all for a name it keeps getting wrong.' +
      (wordLevel ? '' : ' This model gave line timings only, so the gold highlight moves evenly through each line.'),
      'info',
    );
  } catch (error) {
    if (controller.signal.aborted) showStatus('Captions cancelled.', 'info');
    else showStatus(`Captions failed: ${error.message}`, 'error');
  } finally {
    state.captioning = null;
    setCaptioning(false);
  }
});

ui.captionCancel.addEventListener('click', () => state.captioning?.abort());

ui.srt.addEventListener('change', async () => {
  const file = ui.srt.files[0];
  ui.srt.value = '';
  if (!file || !state.project) return;
  const segments = segmentsFromSrt(await file.text());
  if (!segments.length) {
    showStatus(`No captions could be read from "${file.name}". Is it an .srt or .vtt file?`, 'error');
    return;
  }
  setSegments(segments);
  showStatus(`${segments.length} caption lines imported from ${file.name}.`, 'info');
});

ui.captionsOn.addEventListener('change', () => {
  if (state.project) state.project.captions.enabled = ui.captionsOn.checked;
  clearResult();
});

ui.replaceForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const { project } = state;
  if (!project) return;
  const find = ui.replaceFind.value.trim();
  if (!find) return;
  const { segments, count } = replaceEverywhere(project.captions.segments, find, ui.replaceWith.value);
  if (!count) {
    showStatus(`"${find}" doesn't appear in the captions.`, 'info');
    return;
  }
  setSegments(segments);
  showStatus(`Replaced "${find}" in ${count} place${count === 1 ? '' : 's'}.`, 'info');
});

// --- Opening a video ---------------------------------------------------------

function resetVideo() {
  if (state.video) {
    state.video.pause();
    state.video.removeAttribute('src');
    state.video.load();
  }
  if (state.videoUrl) URL.revokeObjectURL(state.videoUrl);
  state.video = null;
  state.videoUrl = null;
}

function openFile(file) {
  if (!file) return;
  if (file.type && !file.type.startsWith('video/')) {
    showStatus(`"${file.name}" doesn't look like a video file.`, 'error');
    return;
  }
  state.captioning?.abort();
  resetVideo();
  clearResult();
  showStatus('Opening…');

  const video = document.createElement('video');
  video.playsInline = true;
  video.preload = 'auto';
  state.videoUrl = URL.createObjectURL(file);
  video.src = state.videoUrl;

  video.addEventListener('loadedmetadata', () => {
    if (!Number.isFinite(video.duration) || !video.videoWidth) {
      showStatus(`This browser can't play "${file.name}". Try an MP4 file.`, 'error');
      return;
    }
    const previous = state.project;
    const project = createProject(file, video.duration, video.videoWidth, video.videoHeight);
    // Keep the look the user has already set up when they switch videos.
    if (previous) {
      Object.assign(project, {
        format: previous.format, framing: previous.framing,
        headline: previous.headline, logo: previous.logo,
      });
    } else {
      project.format = document.querySelector('input[name="format"]:checked').value;
      project.framing = document.querySelector('input[name="framing"]:checked').value;
      project.headline = ui.headline.value;
      project.logo = ui.logo.value;
    }
    project.captions.enabled = ui.captionsOn.checked;
    state.project = project;
    state.video = video;

    ui.drop.hidden = true;
    ui.viewer.hidden = false;
    ui.exportButton.disabled = false;
    sizePreviewCanvas();
    timeline.setProject(project);
    renderCuts();
    renderTranscript();
    ui.autoCaptions.disabled = false;
    showStatus('');
  }, { once: true });

  video.addEventListener('error', () => {
    showStatus(`This browser can't open "${file.name}". Try an MP4 file.`, 'error');
  }, { once: true });

  video.addEventListener('play', () => { ui.play.textContent = '❚❚'; ui.play.setAttribute('aria-label', 'Pause'); });
  video.addEventListener('pause', () => { ui.play.textContent = '▶'; ui.play.setAttribute('aria-label', 'Play'); });
}

ui.file.addEventListener('change', () => openFile(ui.file.files[0]));

['dragenter', 'dragover'].forEach((type) => document.addEventListener(type, (event) => {
  event.preventDefault();
  ui.drop.classList.add('is-over');
}));
['dragleave', 'drop'].forEach((type) => document.addEventListener(type, (event) => {
  event.preventDefault();
  ui.drop.classList.remove('is-over');
}));
document.addEventListener('drop', (event) => openFile(event.dataTransfer?.files?.[0]));

// --- Playback ----------------------------------------------------------------

function togglePlay() {
  const { video, project } = state;
  if (!video || !project) return;
  if (video.paused) {
    const start = nextPlayableTime(project, video.currentTime);
    video.currentTime = start === null ? project.trim.start : start;
    video.play().catch(() => {});
  } else {
    video.pause();
  }
}

ui.play.addEventListener('click', togglePlay);
document.addEventListener('keydown', (event) => {
  const typing = event.target.closest('input, select, textarea, button');
  if (event.code === 'Space' && !typing) {
    event.preventDefault();
    togglePlay();
  }
});

// --- Style controls ----------------------------------------------------------

document.addEventListener('change', (event) => {
  const { project } = state;
  if (event.target.name === 'format') {
    if (project) project.format = event.target.value;
    sizePreviewCanvas();
    clearResult();
  } else if (event.target.name === 'framing') {
    if (project) project.framing = event.target.value;
    clearResult();
  } else if (event.target === ui.logo) {
    if (project) project.logo = ui.logo.value;
    clearResult();
  }
});

ui.headline.addEventListener('input', () => {
  if (state.project) state.project.headline = ui.headline.value;
  clearResult();
});

// --- Export ------------------------------------------------------------------

function clearResult() {
  if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
  state.resultUrl = null;
  ui.result.hidden = true;
  ui.result.replaceChildren();
}

function setExporting(active) {
  ui.exportButton.disabled = active || !state.project;
  ui.exportButton.textContent = active ? 'Exporting…' : 'Export MP4';
  ui.progress.hidden = !active;
}

function downloadName(project) {
  const base = project.file.name.replace(/\.[^.]+$/, '').replace(/[^\w-]+/g, '-').slice(0, 60) || 'video';
  return `${base}-${project.format.replace(':', 'x')}.mp4`;
}

ui.exportButton.addEventListener('click', async () => {
  const { project } = state;
  if (!project || state.exporting) return;
  if (!keptRanges(project).length) {
    showStatus('Nothing is left to export — put a removed part back or widen the trim.', 'error');
    return;
  }

  state.video?.pause();
  clearResult();
  showStatus('');
  const controller = new AbortController();
  state.exporting = controller;
  setExporting(true);
  ui.progressFill.style.width = '0%';

  const started = performance.now();
  try {
    const result = await exportVideo(project, state.assets, {
      signal: controller.signal,
      onProgress: (fraction, message) => {
        ui.progressFill.style.width = `${Math.round(fraction * 100)}%`;
        ui.progressText.textContent = `${message} — ${Math.round(fraction * 100)}%`;
      },
    });

    state.resultUrl = URL.createObjectURL(result.blob);
    const seconds = ((performance.now() - started) / 1000).toFixed(0);
    const megabytes = (result.blob.size / 1e6).toFixed(1);
    const link = document.createElement('a');
    link.href = state.resultUrl;
    link.download = downloadName(project);
    link.className = 'button button-primary button-wide';
    link.textContent = `Download ${link.download}`;

    const summary = document.createElement('p');
    summary.className = 'hint';
    summary.textContent = `${formatTime(result.duration)} long · ${megabytes} MB · ` +
      `${result.videoCodec.toUpperCase()}${result.audioCodec ? ` + ${result.audioCodec.toUpperCase()}` : ', no sound'} · ` +
      `made in ${seconds}s`;

    ui.result.replaceChildren(link, summary);
    for (const warning of result.warnings) {
      const note = document.createElement('p');
      note.className = 'notice notice-warn';
      note.textContent = warning;
      ui.result.append(note);
    }
    ui.result.hidden = false;
    link.click();
  } catch (error) {
    if (controller.signal.aborted) showStatus('Export cancelled.', 'info');
    else showStatus(`Export failed: ${error.message}`, 'error');
  } finally {
    state.exporting = null;
    setExporting(false);
  }
});

ui.cancel.addEventListener('click', () => state.exporting?.abort());

// --- Start -------------------------------------------------------------------

buildFormatChoices();
sizePreviewCanvas();

if (!browserSupported()) {
  ui.unsupported.hidden = false;
  ui.file.disabled = true;
} else {
  loadAssets().then((assets) => { state.assets = assets; }).catch(() => {
    showStatus("The brand fonts didn't load, so headlines will use a fallback font.", 'warn');
  });
  // Warm the video engine in the background so the first export starts
  // promptly; a failure here is reported when the user actually exports.
  loadMediabunny().catch(() => {});
}

requestAnimationFrame(tick);

// Exposed for automated tests, which drive the editor without a mouse.
window.__studio = { state, openFile, timeline };
