import React, { useEffect } from 'react';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import { useNavigate } from 'react-router-dom';

export const WorldTimeline: React.FC = () => {
  const navigate = useNavigate();
  const { 
    timelineEvents, 
    activeTimelineEventId, 
    setActiveTimelineEvent,
    activeWorldId,
    fetchTimelineForWorld,
    setActiveManuscript,
    setActiveChapter 
  } = useWorldStore();

  useEffect(() => {
    if (activeWorldId) {
      fetchTimelineForWorld(activeWorldId);
    }
  }, [activeWorldId, fetchTimelineForWorld]);

  const selectedEvent = timelineEvents.find(e => e.id === activeTimelineEventId) || timelineEvents[0];

  const handleSelectEvent = (id: string) => {
    setActiveTimelineEvent(id);
  };

  const navigateToChapter = (chapterId: string) => {
    setActiveManuscript('ms-1');
    setActiveChapter(chapterId);
    navigate(`/worlds/${activeWorldId}/manuscripts/ms-1`);
  };

  return (
    <AppShell>
      {/* Background radial effects */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-surface-container-high/20 via-void-black to-void-black -z-10 pointer-events-none"></div>

      <main className="flex-1 h-screen flex relative overflow-hidden select-none">
        
        {/* Timeline Canvas (Scrollable) */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden relative scroll-smooth px-8 py-12 scrollbar-hide">
          <div className="max-w-4xl mx-auto relative min-h-full pb-32 pt-6">
            
            {/* Page Header */}
            <header className="mb-14 max-w-2xl">
              <div className="flex items-center gap-3 mb-3">
                <span className="material-symbols-outlined text-copper-glow text-2xl font-light">timeline</span>
                <h1 className="font-display-lg text-display-lg text-starlight-white">Chronicle Timeline</h1>
              </div>
              <p className="font-body-lg text-body-lg text-on-surface-variant/80 leading-relaxed">
                Track how world parameters, faction controls, and character states transition across chronological milestones.
              </p>
            </header>

            {/* The Central Line */}
            <div className="absolute left-[50%] top-44 bottom-24 w-[1px] timeline-line -translate-x-1/2 z-0" />

            {/* Timeline Events Stack */}
            <div className="relative z-10 flex flex-col gap-20 mt-12">
              {timelineEvents.map((event, idx) => {
                const isLeft = idx % 2 === 0;
                const isActive = event.id === activeTimelineEventId;

                return (
                  <div 
                    key={event.id}
                    onClick={() => handleSelectEvent(event.id)}
                    className={`flex items-center w-full relative group cursor-pointer ${
                      isLeft ? 'justify-end pr-12 text-right w-1/2' : 'justify-start pl-12 ml-auto w-1/2 text-left'
                    }`}
                  >
                    {/* Node Dot Indicator */}
                    <div 
                      className={`absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border border-background transition-all duration-300 z-20 ${
                        isLeft ? 'right-[-6px]' : 'left-[-6px]'
                      } ${
                        isActive 
                          ? 'bg-primary timeline-node-active scale-125 border-primary shadow-[0_0_12px_rgba(254,182,141,0.8)]' 
                          : 'bg-outline-variant group-hover:bg-primary'
                      }`}
                    />
                    
                    {/* Active Halo Glow */}
                    {isActive && (
                      <div className={`absolute top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-primary/15 blur-[6px] z-10 pointer-events-none ${
                        isLeft ? 'right-[-20px]' : 'left-[-20px]'
                      }`} />
                    )}

                    {/* Event Info Block */}
                    <div className={`transition-all duration-300 w-full max-w-md ${
                      isActive 
                        ? 'glass-card p-5 rounded-xl border border-primary/30 relative overflow-hidden shadow-2xl scale-[1.02]' 
                        : 'opacity-65 hover:opacity-100'
                    }`}>
                      {isActive && (
                        <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent pointer-events-none" />
                      )}
                      
                      <span className={`font-label-sm text-[10px] uppercase tracking-widest block mb-1.5 ${isActive ? 'text-primary' : 'text-primary/60'}`}>
                        Chapter {event.year} • {event.period}
                      </span>
                      
                      <h3 className={`font-headline-md text-headline-md group-hover:text-primary transition-colors text-base font-bold ${
                        isActive ? 'text-starlight-white' : 'text-on-surface'
                      }`}>
                        {event.title}
                      </h3>
                      
                      <p className="font-body-md text-xs text-on-surface-variant/80 mt-2 leading-relaxed">
                        {event.description}
                      </p>

                      {isActive && (
                        <div className="mt-4 flex items-center gap-1.5 text-primary/80 font-label-sm text-[10px] uppercase tracking-widest">
                          <span className="material-symbols-outlined text-sm font-light">visibility</span>
                          Viewing Parameter Changes
                        </div>
                      )}
                    </div>

                  </div>
                );
              })}
            </div>

          </div>
        </div>

        {/* Dynamic World State Changes wing inside the main stage (Right side wing) */}
        <aside className="w-[340px] bg-surface-container-low/95 border-l border-starlight-white/10 flex flex-col h-full shrink-0 z-20">
          
          {/* Header */}
          <div className="p-6 border-b border-starlight-white/5 bg-gradient-to-b from-surface-container-highest/20 to-transparent pt-14">
            <span className="font-label-sm text-[10px] text-primary/70 block mb-1 tracking-wider uppercase">Event Chronicle</span>
            <h2 className="font-headline-md text-headline-md text-starlight-white leading-tight text-lg">
              {selectedEvent?.title}
            </h2>
            <p className="font-label-sm text-[10px] text-on-surface-variant/50 uppercase tracking-widest mt-1">
              Chapter {selectedEvent?.year} • {selectedEvent?.period}
            </p>
          </div>

          {/* Details Scroll */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            
            {/* World State Changes */}
            <div className="space-y-4">
              <h3 className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider flex items-center gap-2 border-b border-starlight-white/5 pb-2">
                <span className="material-symbols-outlined text-[16px] font-light">compare_arrows</span>
                State Parameters
              </h3>
              
              <div className="space-y-3">
                {selectedEvent?.stateChanges.map((change, idx) => (
                  <div key={idx} className="bg-surface-container/40 p-4 rounded-lg border border-starlight-white/5 relative overflow-hidden">
                    <div className="flex items-center gap-2.5 mb-3">
                      <span className="material-symbols-outlined text-sm text-primary font-light">
                        {change.entityType === 'character' ? 'person' : 'location_on'}
                      </span>
                      <span className="font-body-md text-xs text-starlight-white font-medium">{change.entityName}</span>
                    </div>

                    <div className="grid grid-cols-2 gap-2 relative text-xs">
                      {/* Arrow divider */}
                      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-outline-variant/20 -translate-x-1/2"></div>
                      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 bg-void-black rounded-full border border-starlight-white/10 flex items-center justify-center">
                        <span className="material-symbols-outlined text-[10px] text-on-surface-variant font-light">arrow_forward</span>
                      </div>

                      <div className="pr-3 text-right">
                        <span className="font-label-sm text-[9px] text-on-surface-variant/40 block mb-0.5 uppercase tracking-wider">{change.field} (Before)</span>
                        <span className="text-on-surface-variant/80 font-medium truncate block">{change.before}</span>
                      </div>
                      <div className="pl-5 text-left">
                        <span className="font-label-sm text-[9px] text-primary/50 block mb-0.5 uppercase tracking-wider">{change.field} (After)</span>
                        <span className="text-primary font-semibold truncate block">{change.after}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Mentioned In */}
            <div className="space-y-3">
              <h3 className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider border-b border-starlight-white/5 pb-2">
                Source Manuscripts
              </h3>
              {selectedEvent?.chapters.length === 0 ? (
                <p className="text-xs text-on-surface-variant/40 italic">No manuscript mentions linked.</p>
              ) : (
                selectedEvent?.chapters.map(ch => (
                  <button
                    key={ch.id}
                    onClick={() => navigateToChapter(ch.id)}
                    className="w-full text-left p-3 rounded-lg border border-starlight-white/5 hover:border-primary/30 hover:bg-white/5 transition-all flex items-center gap-3 group"
                  >
                    <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors text-lg font-light">menu_book</span>
                    <div className="min-w-0">
                      <span className="block font-body-md text-xs text-starlight-white group-hover:text-primary transition-colors truncate">The Ash Chronicles</span>
                      <span className="block font-label-sm text-[10px] text-on-surface-variant/50 mt-0.5 truncate">{ch.name}</span>
                    </div>
                  </button>
                ))
              )}
            </div>

          </div>
        </aside>

      </main>
    </AppShell>
  );
};
