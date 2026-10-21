import React, { useEffect, useState } from 'react';
import { Dialog } from './Dialog';
import { useNavigate } from 'react-router-dom';
import { deleteWorld, getProfile, getWorld, updateProfile, updateWorld } from '../api/account';
import type { Preferences } from '../api/account';
import { useWorldStore } from '../store/useWorldStore';

const field = 'w-full bg-surface-container-lowest border border-starlight-white/10 rounded-lg px-3 py-2 text-sm text-starlight-white focus:border-primary focus:outline-none';
const label = 'font-label-sm text-[10px] uppercase tracking-widest text-on-surface-variant/60 mb-1 block';

/** Archive settings: this world's name and description, deleting it, and the creator's preferences. */
export const SettingsModal: React.FC<{ worldId: string | null; onClose: () => void }> = ({ worldId, onClose }) => {
  const navigate = useNavigate();
  const { setActiveWorld } = useWorldStore();
  const realWorld = worldId && !worldId.startsWith('terra-') ? worldId : null;
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirm, setConfirm] = useState('');
  const [originalName, setOriginalName] = useState('');

  useEffect(() => {
    getProfile().then((p) => setPrefs(p.preferences)).catch(error => setMessage({ ok: false, text: error.message }));
    if (realWorld) {
      getWorld(realWorld).then((w) => { setName(w.name); setOriginalName(w.name); setDescription(w.description || ''); })
        .catch(error => setMessage({ ok: false, text: error.message }));
    }
  }, [realWorld]);

  const flash = (ok: boolean, text: string) => {
    setMessage({ ok, text });
    setTimeout(() => setMessage(null), 2500);
  };

  const saveWorld = async () => {
    if (!realWorld) return;
    try {
      const w = await updateWorld(realWorld, { name, description });
      setOriginalName(w.name);
      setName(w.name);
      setDescription(w.description);
      useWorldStore.setState(state => ({ worlds: state.worlds.map(world => world.id === realWorld ? { ...world, name: w.name, description: w.description } : world) }));
      flash(true, 'World saved.');
    } catch (e: any) {
      flash(false, e.message);
    }
  };

  const setPref = async (patch: Partial<Preferences>) => {
    try {
      const p = await updateProfile({ preferences: patch });
      setPrefs(p.preferences);
    } catch (e: any) {
      flash(false, e.message);
    }
  };

  const removeWorld = async () => {
    if (!realWorld || confirm !== originalName) return;
    try {
      await deleteWorld(realWorld);
      setActiveWorld(null);
      onClose();
      navigate('/worlds');
    } catch (e: any) {
      flash(false, e.message);
    }
  };

  return (
    <Dialog title="Archive Settings" onClose={onClose}>
        <div className="space-y-8">
          {message && <p className={`text-sm ${message.ok ? 'text-emerald-400' : 'text-red-300'}`}>{message.text}</p>}

          {realWorld && (
            <section className="space-y-3">
              <h3 className="text-sm text-starlight-white font-semibold">This world</h3>
              <div>
                <span className={label}>Name</span>
                <input aria-label="World name" className={field} value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div>
                <span className={label}>Description</span>
                <textarea aria-label="World description" className={`${field} h-20 resize-none`} value={description} onChange={(e) => setDescription(e.target.value)} />
              </div>
              <div className="flex justify-end">
                <button onClick={saveWorld} disabled={!name.trim()} className="px-4 py-1.5 rounded-lg text-sm bg-primary/20 text-primary border border-primary/50 hover:bg-primary hover:text-void-black transition-colors disabled:opacity-40">
                  Save world
                </button>
              </div>
            </section>
          )}

          <section className="space-y-4">
            <h3 className="text-sm text-starlight-white font-semibold">Preferences</h3>
            {!prefs ? <p className="text-sm text-on-surface-variant/60">Loading…</p> : (
              <>
                <div>
                  <span className={label}>Character chat replies</span>
                  <div className="flex gap-2">
                    {(['short', 'medium', 'long'] as const).map((len) => (
                      <button key={len} onClick={() => setPref({ chat_reply_length: len })}
                        className={`px-4 py-1.5 rounded-full border text-xs capitalize transition-all ${
                          prefs.chat_reply_length === len ? 'border-copper-glow text-copper-glow bg-copper-glow/5' : 'border-starlight-white/10 text-on-surface-variant/70 hover:text-starlight-white'}`}>
                        {len}
                      </button>
                    ))}
                  </div>
                </div>
                <label className="flex items-start gap-3 cursor-pointer">
                  <input type="checkbox" className="mt-1 accent-[#eba686]" checked={prefs.review_preselect_new}
                    onChange={(e) => setPref({ review_preselect_new: e.target.checked })} />
                  <span className="text-sm text-starlight-white/90">
                    Tick new items in the re-extraction review
                    <span className="block text-[11px] text-on-surface-variant/60">Off: you tick each new entity, fact or event yourself before applying.</span>
                  </span>
                </label>
              </>
            )}
          </section>

          {realWorld && (
            <section className="space-y-2 pt-4 border-t border-red-400/20">
              <h3 className="text-sm text-red-300 font-semibold">Delete this world</h3>
              <p className="text-xs text-on-surface-variant/70">
                Deletes its manuscripts, chapters, entities, relationships, events and contradictions. This can't be undone.
                Type <span className="text-starlight-white font-semibold">{originalName}</span> to confirm.
              </p>
              <div className="flex gap-2">
                <input aria-label="Confirm world deletion" className={field} value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder={originalName} />
                <button onClick={removeWorld} disabled={confirm !== originalName}
                  className="px-4 rounded-lg text-sm bg-red-500/10 text-red-300 border border-red-400/40 hover:bg-red-500/30 transition-colors disabled:opacity-40">
                  Delete
                </button>
              </div>
            </section>
          )}

          <div className="pt-4 border-t border-starlight-white/5 flex justify-end">
            <button onClick={() => { setActiveWorld(null); onClose(); navigate('/worlds'); }}
              className="px-4 py-1.5 rounded-lg text-sm text-starlight-white/70 hover:text-primary hover:bg-surface-container-highest transition-colors flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[18px]">arrow_back</span> Back to all worlds
            </button>
          </div>
        </div>
    </Dialog>
  );
};
