import { ChevronLeft, ChevronRight, Image, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

export function ScreenshotGallery({ screenshots }: { screenshots: string[] }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const uniqueScreenshots = useMemo(() => Array.from(new Set(screenshots)), [screenshots]);
  const activeSrc = activeIndex === null ? null : uniqueScreenshots[activeIndex];

  useEffect(() => {
    if (activeIndex !== null && activeIndex >= uniqueScreenshots.length) {
      setActiveIndex(null);
    }
  }, [activeIndex, uniqueScreenshots.length]);

  useEffect(() => {
    if (activeIndex === null) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setActiveIndex(null);
      }
      if (event.key === 'ArrowLeft') {
        setActiveIndex((index) => previousIndex(index, uniqueScreenshots.length));
      }
      if (event.key === 'ArrowRight') {
        setActiveIndex((index) => nextIndex(index, uniqueScreenshots.length));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeIndex, uniqueScreenshots.length]);

  if (screenshots.length === 0) {
    return <div className="empty-state"><Image size={18} /> Screenshots will appear after browser steps run.</div>;
  }

  return (
    <>
      <div className="screenshot-grid">
        {uniqueScreenshots.map((src, index) => (
          <button className="screenshot-thumb" type="button" onClick={() => setActiveIndex(index)} key={`${src}-${index}`}>
            <img src={src} alt={fileName(src)} />
            <span>{fileName(src)}</span>
          </button>
        ))}
      </div>

      {activeSrc ? (
        <div className="screenshot-lightbox" role="dialog" aria-modal="true" aria-label="Screenshot preview">
          <div className="lightbox-toolbar">
            <span>{fileName(activeSrc)}</span>
            <button type="button" className="icon-button" onClick={() => setActiveIndex(null)} aria-label="Close preview">
              <X size={18} />
            </button>
          </div>
          <button
            type="button"
            className="lightbox-nav previous"
            onClick={() => setActiveIndex((index) => previousIndex(index, uniqueScreenshots.length))}
            aria-label="Previous screenshot"
          >
            <ChevronLeft size={22} />
          </button>
          <img src={activeSrc} alt={fileName(activeSrc)} />
          <button
            type="button"
            className="lightbox-nav next"
            onClick={() => setActiveIndex((index) => nextIndex(index, uniqueScreenshots.length))}
            aria-label="Next screenshot"
          >
            <ChevronRight size={22} />
          </button>
        </div>
      ) : null}
    </>
  );
}

function fileName(src: string) {
  const parts = src.split('/');
  return parts[parts.length - 1] || 'QA screenshot';
}

function previousIndex(index: number | null, length: number) {
  if (index === null || length === 0) {
    return null;
  }
  return (index - 1 + length) % length;
}

function nextIndex(index: number | null, length: number) {
  if (index === null || length === 0) {
    return null;
  }
  return (index + 1) % length;
}
