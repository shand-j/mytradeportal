/**
 * Media slot for app demo footage.
 *
 * Default renders the real product screen (poster) in a chrome-free frame —
 * Hallmark gate 57: no re-drawn fake device chrome. When the AI-generated
 * iPhone renders arrive, pass `frameSrc` (render image) plus `screenInset`
 * (percent inset of the screen area within the render) and the video/poster
 * is composited into the render's screen.
 */
type MediaSlotProps = {
  posterSrc: string;
  videoSrc?: string;
  frameSrc?: string;
  screenInset?: { top: number; right: number; bottom: number; left: number };
  alt: string;
  aspect?: string;
};

export function MediaSlot({
  posterSrc,
  videoSrc,
  frameSrc,
  screenInset = { top: 0, right: 0, bottom: 0, left: 0 },
  alt,
  aspect = "9 / 19.5",
}: MediaSlotProps) {
  const media = videoSrc ? (
    <video
      src={videoSrc}
      poster={posterSrc}
      autoPlay
      loop
      muted
      playsInline
      aria-label={alt}
    />
  ) : (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={posterSrc} alt={alt} loading="lazy" />
  );

  if (!frameSrc) {
    return (
      <figure className="media-slot" style={{ aspectRatio: aspect }}>
        {media}
      </figure>
    );
  }

  return (
    <figure className="media-slot media-slot-framed" style={{ aspectRatio: aspect }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="media-frame" src={frameSrc} alt="" aria-hidden />
      <div
        className="media-screen"
        style={{
          top: `${screenInset.top}%`,
          right: `${screenInset.right}%`,
          bottom: `${screenInset.bottom}%`,
          left: `${screenInset.left}%`,
        }}
      >
        {media}
      </div>
    </figure>
  );
}
