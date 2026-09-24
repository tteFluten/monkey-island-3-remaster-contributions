import { useState, useEffect, useRef, useCallback } from 'react';
import type { Asset, SceneManifest } from '@shared/types';
import { startGeneration, subscribeJobEvents } from '../lib/api';

export interface QueueItem {
  asset: Asset;
  scene: SceneManifest;
  status: 'pending' | 'sending' | 'generating' | 'saving' | 'completed' | 'failed';
  error?: string;
}

interface Props {
  items: { asset: Asset; scene: SceneManifest }[];
  prompt: string;
  model: string;
  onClose: () => void;
  onRefresh: () => void;
}

export function BatchQueue({ items, prompt, model, onClose, onRefresh }: Props) {
  const [queue, setQueue] = useState<QueueItem[]>(() =>
    items.map(i => ({ ...i, status: 'pending' as const }))
  );
  const [running, setRunning] = useState(true);
  const cancelled = useRef(false);
  const currentIdx = useRef(0);

  const completed = queue.filter(q => q.status === 'completed').length;
  const failed = queue.filter(q => q.status === 'failed').length;
  const total = queue.length;
  const progress = ((completed + failed) / total) * 100;

  const processNext = useCallback(async () => {
    while (currentIdx.current < queue.length && !cancelled.current) {
      const idx = currentIdx.current;
      const item = queue[idx];

      // Update status
      setQueue(prev => {
        const next = [...prev];
        next[idx] = { ...next[idx], status: 'sending' };
        return next;
      });

      try {
        const isGemini = model.startsWith('gemini');
        // Compute aspect ratio
        const w = item.asset.width;
        const h = item.asset.height;
        const r = w / h;
        let aspectRatio = '4:3';
        if (r > 1.5) aspectRatio = '16:9';
        else if (r > 1.2) aspectRatio = '4:3';
        else if (r > 0.9) aspectRatio = '1:1';
        else aspectRatio = '3:4';

        const job = await startGeneration({
          sceneId: item.scene.scene.id,
          assetId: item.asset.id,
          prompt,
          model,
          aspectRatio,
          imageSize: isGemini ? '4K' : '1K',
          references: [{ position: 1, assetId: item.asset.id, label: 'background' }],
        });

        // Wait for job completion via SSE
        await new Promise<void>((resolve, reject) => {
          const unsub = subscribeJobEvents(job.id, (data: any) => {
            if (data.status && data.status !== 'completed' && data.status !== 'failed') {
              setQueue(prev => {
                const next = [...prev];
                next[idx] = { ...next[idx], status: data.status };
                return next;
              });
            }
            if (data.status === 'completed') {
              setQueue(prev => {
                const next = [...prev];
                next[idx] = { ...next[idx], status: 'completed' };
                return next;
              });
              unsub();
              resolve();
            } else if (data.status === 'failed') {
              setQueue(prev => {
                const next = [...prev];
                next[idx] = { ...next[idx], status: 'failed', error: data.error };
                return next;
              });
              unsub();
              resolve(); // don't reject, continue queue
            }
          });

          // Timeout after 3 minutes
          setTimeout(() => {
            unsub();
            setQueue(prev => {
              const next = [...prev];
              if (next[idx].status !== 'completed' && next[idx].status !== 'failed') {
                next[idx] = { ...next[idx], status: 'failed', error: 'Timeout (3m)' };
              }
              return next;
            });
            resolve();
          }, 180000);
        });

      } catch (err) {
        setQueue(prev => {
          const next = [...prev];
          next[idx] = { ...next[idx], status: 'failed', error: String(err) };
          return next;
        });
      }

      currentIdx.current++;
    }

    setRunning(false);
    onRefresh();
  }, []);  // eslint-disable-line -- stable refs

  useEffect(() => {
    processNext();
    return () => { cancelled.current = true; };
  }, [processNext]);

  function handleCancel() {
    cancelled.current = true;
    setRunning(false);
  }

  return (
    <div className="batch-overlay">
      <div className="batch-panel">
        <div className="batch-header">
          <strong>Batch Generation</strong>
          <span className="batch-stats">
            {completed}/{total} done
            {failed > 0 && <span className="batch-failed"> &middot; {failed} failed</span>}
          </span>
          <div style={{ flex: 1 }} />
          {running ? (
            <button className="detail-btn" onClick={handleCancel}>Cancel</button>
          ) : (
            <button className="detail-btn" onClick={onClose}>Close</button>
          )}
        </div>

        {/* Progress bar */}
        <div className="batch-progress-track">
          <div
            className="batch-progress-fill"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Queue list */}
        <div className="batch-list">
          {queue.map((item, i) => (
            <div key={item.asset.id} className={`batch-item ${item.status}`}>
              <span className="batch-item-idx">{i + 1}</span>
              <span className="batch-item-name">{item.asset.name}</span>
              <span className="batch-item-dims">{item.asset.width}&times;{item.asset.height}</span>
              <span className={`batch-item-status status-${item.status}`}>
                {item.status === 'pending' && 'Waiting'}
                {item.status === 'sending' && 'Sending...'}
                {item.status === 'generating' && 'Generating...'}
                {item.status === 'saving' && 'Saving...'}
                {item.status === 'completed' && 'Done'}
                {item.status === 'failed' && (item.error?.slice(0, 60) || 'Failed')}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
