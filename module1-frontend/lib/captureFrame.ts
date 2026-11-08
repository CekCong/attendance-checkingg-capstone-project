/**
 * Capture a single JPEG frame from a live video element into an in-memory Base64 string.
 * The canvas is never mounted visibly, and the result must not be persisted or rendered as an <img>.
 */
export function captureFrameAsBase64(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  quality = 0.92,
): string {
  const width = video.videoWidth;
  const height = video.videoHeight;

  if (!width || !height) {
    throw new Error(
      "Camera stream is not ready. Please wait a moment and try again.",
    );
  }

  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("Unable to allocate a drawing context for frame capture.");
  }

  // Mirror only the preview, not the image submitted to the recognition model.
  ctx.drawImage(video, 0, 0, width, height);

  const dataUrl = canvas.toDataURL("image/jpeg", quality);

  // Clear pixel buffer immediately so the canvas does not retain the frame.
  ctx.clearRect(0, 0, width, height);

  return dataUrl;
}
