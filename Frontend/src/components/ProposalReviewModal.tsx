import React, { useEffect, useMemo, useState } from 'react';
import { getProfile } from '../api/account';
import { applyProposals, PROPOSAL_APPLY_ORDER } from '../api/proposals';
import type { ApplyResult, EntityRef, Proposal } from '../api/proposals';
import { Dialog } from './Dialog';

interface Props {
  worldId: string;
  chapterNumber: number | null;
  proposals: Proposal[];
  onClose: (applied: boolean) => void;
}

const KIND_LABEL: Record<Proposal['kind'], string> = {
  entity: 'Entities', alias: 'Aliases', fact: 'Facts', relationship: 'Relationships', event: 'Events',
};

/** The entity proposals a proposal depends on (through entity_ref). */
const refsOf = (p: Proposal): string[] => {
  const refs: EntityRef[] =
    p.kind === 'fact' ? [p.entity] :
    p.kind === 'relationship' ? [p.source, p.target] :
    p.kind === 'event' ? p.participants.map((x) => x.entity) : [];
  return refs.flatMap((r) => ('entity_ref' in r ? [r.entity_ref] : []));
};

/**
 * Re-extraction review (docs/api.md §17): the world state the author has accepted is the truth, so nothing is written
 * until they tick it. New items start ticked; a changed value starts on "keep old".
 */
export const ProposalReviewModal: React.FC<Props> = ({ worldId, chapterNumber, proposals, onClose }) => {
  const shown = useMemo(() => proposals.filter((p) => p.change !== 'known'), [proposals]);
  const [accepted, setAccepted] = useState<Set<string>>(new Set());
  const [preferencesReady, setPreferencesReady] = useState(false);
  const [preferenceError, setPreferenceError] = useState<string | null>(null);
  useEffect(() => {
    let closed = false;
    getProfile().then(profile => {
      if (!closed && profile.preferences.review_preselect_new) setAccepted(new Set(shown.filter(item => item.change === 'new').map(item => item.id)));
    }).catch(() => { if (!closed) setPreferenceError('Could not load review preferences. Select the changes you want to apply.'); })
      .finally(() => { if (!closed) setPreferencesReady(true); });
    return () => { closed = true; };
  }, [shown]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApplyResult | null>(null);

  // An event can still go in without a rejected participant; a fact or relationship can't
  const blocked = (p: Proposal) => p.kind !== 'event' && refsOf(p).some((r) => !accepted.has(r));
  const toggle = (id: string) => setAccepted((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const knownCount = proposals.length - shown.length;

  const apply = async () => {
    setBusy(true);
    const usable = new Set([...accepted].filter((id) => {
      const p = shown.find((x) => x.id === id);
      return p && !blocked(p);
    }));
    const res = await applyProposals(worldId, proposals, usable);
    setBusy(false);
    setResult(res);
  };

  return (
    <Dialog title={`Review changes${chapterNumber ? ` from chapter ${chapterNumber}` : ''}`} onClose={() => { if (!busy) onClose((result?.applied || 0) > 0); }}>
      <p className="mb-5 text-sm leading-relaxed text-on-surface-variant/70">Your world stays as it is until you apply. {shown.length} proposed changes{knownCount > 0 ? `, ${knownCount} already in your world` : ''}.</p>
      {preferenceError && <p role="alert" className="mb-4 text-sm text-error">{preferenceError}</p>}
        <div className="space-y-6">
          {result ? (
            <div className="space-y-3 text-sm">
              <p className="text-starlight-white">
                Applied {result.applied} change{result.applied === 1 ? '' : 's'}
                {result.skipped ? `, skipped ${result.skipped}` : ''}.
              </p>
              {result.errors.length > 0 && (
                <ul className="list-disc pl-5 text-red-300/90 space-y-1">
                  {result.errors.map((e) => <li key={e}>{e}</li>)}
                </ul>
              )}
            </div>
          ) : shown.length === 0 ? (
            <p className="text-on-surface-variant/70 text-sm">Nothing new: this chapter matches your world.</p>
          ) : (
            PROPOSAL_APPLY_ORDER.map((kind) => {
              const items = shown.filter((p) => p.kind === kind);
              if (items.length === 0) return null;
              return (
                <section key={kind}>
                  <h3 className="font-label-sm text-[10px] uppercase tracking-widest text-primary mb-2">{KIND_LABEL[kind]}</h3>
                  <ul className="space-y-1.5">
                    {items.map((p) => {
                      const off = blocked(p);
                      const isChanged = p.change === 'changed';
                      return (
                        <li key={p.id}>
                          <label className={`flex items-start gap-3 px-3 py-2 rounded-lg border border-starlight-white/5 bg-surface-container-low ${off ? 'opacity-40' : 'cursor-pointer hover:border-primary/30'}`}>
                            <input
                              type="checkbox"
                              className="mt-1 accent-[#eba686]"
                              checked={accepted.has(p.id) && !off}
                              disabled={off || busy || !preferencesReady}
                              onChange={() => toggle(p.id)}
                            />
                            <span className="flex-1 text-sm text-starlight-white/90">
                              {p.summary}
                              <span className="block text-[11px] text-on-surface-variant/60 mt-0.5">
                                {off ? 'Needs the new entity it refers to'
                                  : isChanged ? (accepted.has(p.id) ? 'Keep new value' : 'Keep old value')
                                  : 'New'}
                              </span>
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })
          )}
        </div>

        <div className="mt-6 border-t border-white/5 pt-5 flex justify-end gap-3">
          {result ? (
            <button onClick={() => onClose(result.applied > 0)}
              className="px-4 py-2 rounded-lg font-label-sm text-sm bg-primary/20 text-primary border border-primary/50 hover:bg-primary hover:text-void-black transition-colors">
              Done
            </button>
          ) : (
            <>
              <button onClick={() => onClose(false)} disabled={busy}
                className="px-4 py-2 rounded-lg font-label-sm text-sm text-starlight-white/70 hover:text-starlight-white hover:bg-surface-container-highest transition-colors">
                Discard all
              </button>
              <button onClick={apply} disabled={busy || !preferencesReady || shown.length === 0}
                className="px-4 py-2 rounded-lg font-label-sm text-sm bg-primary/20 text-primary border border-primary/50 hover:bg-primary hover:text-void-black transition-colors disabled:opacity-50">
                {busy ? 'Applying…' : `Apply ${[...accepted].filter((id) => { const p = shown.find((x) => x.id === id); return p && !blocked(p); }).length} selected`}
              </button>
            </>
          )}
        </div>
    </Dialog>
  );
};
