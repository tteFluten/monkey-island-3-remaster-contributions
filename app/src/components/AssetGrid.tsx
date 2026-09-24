import type { Asset, SceneManifest } from '@shared/types';
import { assetFileUrl } from '../lib/api';

interface Props {
  items: { asset: Asset; scene: SceneManifest }[];
  onSelect: (item: { asset: Asset; scene: SceneManifest }) => void;
  selected: Set<string>;
  onToggleSelect: (assetId: string) => void;
  selectMode: boolean;
}

export function AssetGrid({ items, onSelect, selected, onToggleSelect, selectMode }: Props) {
  return (
    <div className="asset-grid">
      {items.map(({ asset, scene }) => {
        const hasHD = asset.variants.length > 0;
        const approved = !!asset.approvedVariantId;
        const isSelected = selected.has(asset.id);
        return (
          <div
            key={asset.id}
            className={`asset-card ${hasHD ? 'has-hd' : ''} ${approved ? 'approved' : ''} ${isSelected ? 'selected' : ''}`}
            onClick={(e) => {
              if (selectMode || e.ctrlKey || e.metaKey) {
                onToggleSelect(asset.id);
              } else {
                onSelect({ asset, scene });
              }
            }}
          >
            {selectMode && (
              <div className="card-check" onClick={(e) => { e.stopPropagation(); onToggleSelect(asset.id); }}>
                {isSelected ? '\u2713' : ''}
              </div>
            )}
            <div className="card-thumb">
              <img
                src={assetFileUrl(asset.originalPath)}
                alt={asset.name}
                loading="lazy"
              />
              {hasHD && (
                <span className={`card-badge ${approved ? 'badge-ok' : 'badge-hd'}`}>
                  {approved ? 'HD Approved' : `${asset.variants.length} HD`}
                </span>
              )}
            </div>
            <div className="card-label">
              <span className="card-name">{asset.name}</span>
              <span className="card-meta">{asset.width}&times;{asset.height}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
