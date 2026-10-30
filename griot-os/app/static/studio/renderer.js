/**
 * Draws one finished frame: the reframed video plus its graphics.
 *
 * The live preview and the exporter both call drawFrame(), so what the user
 * sees while editing is exactly what the export contains. Everything is laid
 * out relative to the canvas, which lets the preview run on a small canvas and
 * the export on a full 1080p one with identical proportions.
 */

import { drawCaptions } from './captions.js';
import { CAPTION_FONT, HEADLINE_FONT, wrapLines } from './text.js';
import { MAIN_TRACK, VIDEO_TRACKS, clipsOn, isActive, joinEffectAt, transitionAt } from './tracks.js';

export const FORMATS = {
  '9:16': { width: 1080, height: 1920, label: 'Vertical 9:16', use: 'Reels · TikTok · Shorts' },
  '1:1': { width: 1080, height: 1080, label: 'Square 1:1', use: 'Instagram · LinkedIn feed' },
  '16:9': { width: 1920, height: 1080, label: 'Widescreen 16:9', use: 'YouTube · presentations' },
};

// SpeakPower brand colours for on-video graphics. The gold is the brighter
// one from the GRIOT mark: the UI's softer gold disappears against footage.
const GOLD = '#E0BE55';
const NAVY_BAND = 'rgba(40, 49, 66, 0.84)';
const WHITE = '#FFFFFF';


// Per-format placement, as fractions of the frame. Vertical video keeps its
// graphics clear of the platform's own header and its caption/username area;
// the other formats have no such overlays to avoid.
// lowerThirdBottom keeps name titles clear of the captions beneath them.
const LAYOUT = {
  '9:16': { headlineTop: 0.208, captionBottom: 0.245, logoTop: 0.12, logoBesideHeadline: false, lowerThirdBottom: 0.37 },
  '1:1': { headlineTop: 0.085, captionBottom: 0.13, logoTop: 0.045, logoBesideHeadline: true, lowerThirdBottom: 0.31 },
  '16:9': { headlineTop: 0.075, captionBottom: 0.11, logoTop: 0.045, logoBesideHeadline: true, lowerThirdBottom: 0.30 },
};

/**
 * Fonts and the logo, loaded once. Fonts are bundled with the app rather than
 * relied on from the system: an office PC will not have Inter installed, and a
 * missing font would silently change the look of every export.
 */
export async function loadAssets(base = '/static/studio') {
  const faces = [
    new FontFace(HEADLINE_FONT, `url(${base}/fonts/Inter-ExtraBold.otf)`),
    new FontFace(CAPTION_FONT, `url(${base}/fonts/Inter-Black.otf)`),
  ];
  await Promise.all(faces.map(async (face) => {
    await face.load();
    document.fonts.add(face);
  }));

  const logo = new Image();
  logo.src = `${base}/brand/speakpower-badge.png`;
  await logo.decode();

  return { logos: { speakpower: logo } };
}

/** Scale (w, h) to fit (W, H): "cover" fills and crops, "contain" fits inside. */
function fit(sourceWidth, sourceHeight, width, height, mode) {
  const scale = mode === 'cover'
    ? Math.max(width / sourceWidth, height / sourceHeight)
    : Math.min(width / sourceWidth, height / sourceHeight);
  const drawWidth = sourceWidth * scale;
  const drawHeight = sourceHeight * scale;
  return { x: (width - drawWidth) / 2, y: (height - drawHeight) / 2, width: drawWidth, height: drawHeight };
}

// Reused scratch canvas for the blurred background, so a long export does not
// allocate a new canvas per frame.
let blurCanvas = null;

function drawBlurredBackground(ctx, source, sourceWidth, sourceHeight, width, height, x = 0, y = 0) {
  // Blur a small copy and stretch it up. Blurring the full 1080x1920 frame
  // every frame is the single most expensive thing a canvas filter can do;
  // at 1/8 size the result is visually the same and many times cheaper.
  const smallWidth = Math.max(16, Math.round(width / 8));
  const smallHeight = Math.max(16, Math.round(height / 8));
  if (!blurCanvas || blurCanvas.width !== smallWidth || blurCanvas.height !== smallHeight) {
    blurCanvas = new OffscreenCanvas(smallWidth, smallHeight);
  }
  const small = blurCanvas.getContext('2d');
  const cover = fit(sourceWidth, sourceHeight, smallWidth, smallHeight, 'cover');
  small.filter = 'blur(3px) brightness(0.72)';
  small.drawImage(source, cover.x, cover.y, cover.width, cover.height);
  small.filter = 'none';

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(blurCanvas, x, y, width, height);
}

function roundedRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function drawHeadline(ctx, text, width, height, unit, layout, logoReserve, alpha) {
  const fontSize = 60 * unit;
  const padX = 30 * unit;
  const padY = 18 * unit;
  const lineHeight = fontSize * 1.18;
  const side = 70 * unit + logoReserve;

  ctx.font = `${fontSize}px ${HEADLINE_FONT}`;
  const lines = wrapLines(ctx, text, width - 2 * side - 2 * padX).slice(0, 3);
  if (!lines.length) return;

  const textWidth = Math.max(...lines.map((line) => ctx.measureText(line).width));
  const boxWidth = textWidth + 2 * padX;
  const boxHeight = lines.length * lineHeight + 2 * padY;
  const boxX = (width - boxWidth) / 2;
  const boxY = height * layout.headlineTop;

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = NAVY_BAND;
  roundedRect(ctx, boxX, boxY, boxWidth, boxHeight, 14 * unit);
  ctx.fill();

  ctx.fillStyle = WHITE;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  lines.forEach((line, index) => {
    ctx.fillText(line, width / 2, boxY + padY + lineHeight * (index + 0.5));
  });
  ctx.restore();
}

/** Draw a picture into a box: cropped to fill it, or whole over a blurred fill. */
function drawPicture(ctx, image, imageWidth, imageHeight, box, mode) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(box.x, box.y, box.width, box.height);
  ctx.clip();
  if (mode === 'contain') {
    drawBlurredBackground(ctx, image, imageWidth, imageHeight, box.width, box.height, box.x, box.y);
  }
  const placed = fit(imageWidth, imageHeight, box.width, box.height, mode);
  ctx.drawImage(image, box.x + placed.x, box.y + placed.y, placed.width, placed.height);
  ctx.restore();
}

/** The box a layer occupies for its layout. */
function layoutBox(layout, size, imageWidth, imageHeight, width, height, unit, frameLayout) {
  switch (layout) {
    case 'top': return { x: 0, y: 0, width, height: height / 2 };
    case 'bottom': return { x: 0, y: height / 2, width, height: height / 2 };
    case 'left': return { x: 0, y: 0, width: width / 2, height };
    case 'right': return { x: width / 2, y: 0, width: width / 2, height };
    case 'pip-tr': case 'pip-tl': case 'pip-br': case 'pip-bl': {
      const aspect = imageHeight / imageWidth || 9 / 16;
      let boxWidth = width * Math.min(0.8, Math.max(0.15, size || 0.36));
      let boxHeight = boxWidth * aspect;
      // A tall or square picture is limited by height, so it never swamps the frame.
      const maxHeight = height * 0.45;
      if (boxHeight > maxHeight) {
        boxHeight = maxHeight;
        boxWidth = boxHeight / aspect;
      }
      const margin = 48 * unit;
      const right = layout.endsWith('r');
      const top = layout.includes('-t');
      // Bottom corners sit just above the captions; top corners below the platform's header.
      const bottomEdge = height * (1 - frameLayout.captionBottom) - 230 * unit;
      return {
        x: right ? width - boxWidth - margin : margin,
        y: top ? height * 0.1 : Math.max(height * 0.1, bottomEdge - boxHeight),
        width: boxWidth,
        height: boxHeight,
        corner: true,
      };
    }
    default: return { x: 0, y: 0, width, height };
  }
}

/** Apply a clip's transition around its drawing: fade, slide, zoom or wipe. */
function withTransition(ctx, transition, box, width, draw) {
  const { type, phase, p } = transition;
  if (p <= 0) return;
  ctx.save();
  if (type === 'fade') {
    ctx.globalAlpha *= p;
  } else if (type === 'slide') {
    // In from the right, out to the left.
    ctx.translate((phase === 'in' ? 1 : -1) * (1 - p) * width, 0);
  } else if (type === 'zoom') {
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    const scale = 0.6 + 0.4 * p;
    ctx.translate(cx, cy);
    ctx.scale(scale, scale);
    ctx.translate(-cx, -cy);
    ctx.globalAlpha *= p;
  } else if (type === 'wipe') {
    ctx.beginPath();
    ctx.rect(box.x, box.y, box.width * p, box.height);
    ctx.clip();
  }
  draw();
  ctx.restore();
}

function drawLayer(ctx, clip, layer, time, width, height, unit, frameLayout) {
  const box = layoutBox(clip.layout, clip.size, layer.width, layer.height, width, height, unit, frameLayout);
  withTransition(ctx, transitionAt(clip, time), box, width, () => {
    if (box.corner) {
      // Picture-in-picture: a framed, rounded window with a soft shadow.
      const radius = 22 * unit;
      ctx.save();
      ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
      ctx.shadowBlur = 30 * unit;
      ctx.shadowOffsetY = 10 * unit;
      ctx.fillStyle = WHITE;
      roundedRect(ctx, box.x - 5 * unit, box.y - 5 * unit, box.width + 10 * unit, box.height + 10 * unit, radius + 5 * unit);
      ctx.fill();
      ctx.restore();
      ctx.save();
      roundedRect(ctx, box.x, box.y, box.width, box.height, radius);
      ctx.clip();
      drawPicture(ctx, layer.image, layer.width, layer.height, box, 'cover');
      ctx.restore();
    } else {
      drawPicture(ctx, layer.image, layer.width, layer.height, box, clip.layout === 'fit' ? 'contain' : 'cover');
    }
  });
}

/** A name title for interviews: navy panel, gold accent bar, name over role. */
function drawLowerThird(ctx, clip, time, width, height, unit, layout) {
  const title = (clip.title || '').trim();
  const subtitle = (clip.subtitle || '').trim();
  if (!title && !subtitle) return;

  const titleSize = 56 * unit;
  const subtitleSize = 36 * unit;
  const padX = 34 * unit;
  const padY = 22 * unit;
  const bar = 12 * unit;
  const maxText = width * 0.78 - 2 * padX - bar;

  ctx.font = `${titleSize}px ${HEADLINE_FONT}`;
  const titleLines = title ? wrapLines(ctx, title, maxText).slice(0, 2) : [];
  const titleWidth = Math.max(0, ...titleLines.map((line) => ctx.measureText(line).width));
  ctx.font = `${subtitleSize}px ${HEADLINE_FONT}`;
  const subtitleLines = subtitle ? wrapLines(ctx, subtitle, maxText).slice(0, 2) : [];
  const subtitleWidth = Math.max(0, ...subtitleLines.map((line) => ctx.measureText(line).width));

  const gap = titleLines.length && subtitleLines.length ? 10 * unit : 0;
  const textHeight = titleLines.length * titleSize * 1.15 + gap + subtitleLines.length * subtitleSize * 1.2;
  const box = {
    x: 60 * unit,
    width: Math.max(titleWidth, subtitleWidth) + 2 * padX + bar,
    height: textHeight + 2 * padY,
  };
  box.y = height - layout.lowerThirdBottom * height - box.height;

  withTransition(ctx, transitionAt(clip, time), box, width, () => {
    ctx.fillStyle = NAVY_BAND;
    roundedRect(ctx, box.x, box.y, box.width, box.height, 12 * unit);
    ctx.fill();
    ctx.fillStyle = GOLD;
    ctx.fillRect(box.x, box.y, bar, box.height);

    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    let y = box.y + padY;
    ctx.fillStyle = WHITE;
    ctx.font = `${titleSize}px ${HEADLINE_FONT}`;
    for (const line of titleLines) {
      ctx.fillText(line, box.x + bar + padX, y + titleSize * 0.575);
      y += titleSize * 1.15;
    }
    y += gap;
    ctx.fillStyle = GOLD;
    ctx.font = `${subtitleSize}px ${HEADLINE_FONT}`;
    for (const line of subtitleLines) {
      ctx.fillText(line, box.x + bar + padX, y + subtitleSize * 0.6);
      y += subtitleSize * 1.2;
    }
  });
}

/**
 * Draw one output frame.
 *
 * @param ctx      2D context of the target canvas (preview or export)
 * @param frame    what to draw at this moment:
 *                   time    -- seconds into the finished video
 *                   source  -- seconds into the main video, or null once it has ended
 *                   main    -- { image, width, height } of the main video, or null
 *                   layers  -- Map(clip id -> { image, width, height }) for video and picture clips
 * @param project  the edit (project.js, tracks.js)
 * @param assets   from loadAssets()
 */
export function drawFrame(ctx, frame, project, assets) {
  const { width, height } = ctx.canvas;
  const unit = Math.min(width, height) / 1080;
  const layout = LAYOUT[project.format] || LAYOUT['9:16'];
  const off = project.trackOff || {};
  const { time } = frame;

  ctx.save();
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, width, height);

  const main = frame.main;
  if (main && main.width && main.height && !off[MAIN_TRACK]) {
    if (project.framing === 'crop') {
      const cover = fit(main.width, main.height, width, height, 'cover');
      ctx.drawImage(main.image, cover.x, cover.y, cover.width, cover.height);
    } else {
      drawBlurredBackground(ctx, main.image, main.width, main.height, width, height);
      const contain = fit(main.width, main.height, width, height, 'contain');
      ctx.drawImage(main.image, contain.x, contain.y, contain.width, contain.height);
    }
    const join = joinEffectAt(project, time);
    if (join) {
      ctx.globalAlpha = join.amount;
      ctx.fillStyle = join.color;
      ctx.fillRect(0, 0, width, height);
      ctx.globalAlpha = 1;
    }
  }
  ctx.restore();

  // V2 up to V8: each higher track draws over the ones below it.
  for (const track of VIDEO_TRACKS) {
    if (off[track]) continue;
    for (const clip of clipsOn(project, track)) {
      if (!isActive(clip, time)) continue;
      if (clip.kind === 'text') {
        drawLowerThird(ctx, clip, time, width, height, unit, layout);
      } else {
        const layer = frame.layers?.get(clip.id);
        if (layer?.image && layer.width && layer.height) drawLayer(ctx, clip, layer, time, width, height, unit, layout);
      }
    }
  }

  const logo = project.logo !== 'none' ? assets?.logos?.[project.logo] : null;
  const logoWidth = 150 * unit;
  const logoMargin = (project.format === '9:16' ? 60 : 40) * unit;

  const headline = (project.headline || '').trim();
  if (headline) {
    // Ease the band in over the first quarter second of the finished video.
    const alpha = Math.min(1, Math.max(0, time / 0.25));
    const reserve = logo && layout.logoBesideHeadline ? logoWidth + logoMargin : 0;
    drawHeadline(ctx, headline, width, height, unit, layout, reserve, alpha);
  }

  // Captions follow the main video's words, so they end when it does.
  if (frame.source !== null && frame.source !== undefined) {
    drawCaptions(ctx, { width, height, unit, layout, times: { source: frame.source, output: time } }, project.captions);
  }

  if (logo) {
    const logoHeight = logoWidth * (logo.naturalHeight / logo.naturalWidth);
    const top = layout.logoTop * height;
    ctx.drawImage(logo, width - logoWidth - logoMargin, top, logoWidth, logoHeight);
  }
}
