/**
 * Draws one finished frame: the reframed video plus its graphics.
 *
 * The live preview and the exporter both call drawFrame(), so what the user
 * sees while editing is exactly what the export contains. Everything is laid
 * out relative to the canvas, which lets the preview run on a small canvas and
 * the export on a full 1080p one with identical proportions.
 */

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

const HEADLINE_FONT = 'StudioInterExtraBold';
export const CAPTION_FONT = 'StudioInterBlack';

// Per-format placement, as fractions of the frame. Vertical video keeps its
// graphics clear of the platform's own header and its caption/username area;
// the other formats have no such overlays to avoid.
const LAYOUT = {
  '9:16': { headlineTop: 0.208, captionBottom: 0.245, logoTop: 0.12, logoBesideHeadline: false },
  '1:1': { headlineTop: 0.085, captionBottom: 0.13, logoTop: 0.045, logoBesideHeadline: true },
  '16:9': { headlineTop: 0.075, captionBottom: 0.11, logoTop: 0.045, logoBesideHeadline: true },
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

function drawBlurredBackground(ctx, source, sourceWidth, sourceHeight, width, height) {
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
  ctx.drawImage(blurCanvas, 0, 0, width, height);
}

/** Break text into lines no wider than maxWidth with the context's font. */
export function wrapLines(ctx, text, maxWidth) {
  const words = text.split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
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

/**
 * Draw one output frame.
 *
 * @param ctx           2D context of the target canvas (preview or export)
 * @param source        the decoded video frame: a <video>, canvas or ImageBitmap
 * @param sourceWidth   source frame width in pixels
 * @param sourceHeight  source frame height in pixels
 * @param times         { source, output } -- seconds in the original, and in the finished video
 * @param project       the edit (see project.js)
 * @param assets        from loadAssets()
 * @param overlays      optional extra drawing, called after the video and before the logo
 */
export function drawFrame(ctx, source, sourceWidth, sourceHeight, times, project, assets, overlays) {
  const { width, height } = ctx.canvas;
  const unit = Math.min(width, height) / 1080;
  const layout = LAYOUT[project.format] || LAYOUT['9:16'];

  ctx.save();
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, width, height);

  if (sourceWidth && sourceHeight) {
    if (project.framing === 'crop') {
      const cover = fit(sourceWidth, sourceHeight, width, height, 'cover');
      ctx.drawImage(source, cover.x, cover.y, cover.width, cover.height);
    } else {
      drawBlurredBackground(ctx, source, sourceWidth, sourceHeight, width, height);
      const contain = fit(sourceWidth, sourceHeight, width, height, 'contain');
      ctx.drawImage(source, contain.x, contain.y, contain.width, contain.height);
    }
  }
  ctx.restore();

  const logo = project.logo !== 'none' ? assets?.logos?.[project.logo] : null;
  const logoWidth = 150 * unit;
  const logoMargin = (project.format === '9:16' ? 60 : 40) * unit;

  const headline = (project.headline || '').trim();
  if (headline) {
    // Ease the band in over the first quarter second of the finished video.
    const alpha = Math.min(1, Math.max(0, (times.output ?? 0) / 0.25));
    const reserve = logo && layout.logoBesideHeadline ? logoWidth + logoMargin : 0;
    drawHeadline(ctx, headline, width, height, unit, layout, reserve, alpha);
  }

  if (overlays) overlays(ctx, { width, height, unit, layout, times });

  if (logo) {
    const logoHeight = logoWidth * (logo.naturalHeight / logo.naturalWidth);
    const top = layout.logoTop * height;
    ctx.drawImage(logo, width - logoWidth - logoMargin, top, logoWidth, logoHeight);
  }
}
