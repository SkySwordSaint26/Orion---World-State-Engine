import React, { useEffect } from 'react';
import { Link, useLocation, useParams, useNavigate } from 'react-router-dom';
import { useWorldStore } from '../store/useWorldStore';
import { AnimatePresence, motion } from 'framer-motion';
import { EntityPanel } from './EntityPanel';

interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const { worldId } = useParams<{ worldId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  
  const { 
    activeEntityId, 
    isEntityPanelOpen, 
    setEntityPanelOpen,
    setActiveWorld,
    activeWorldId,
    contradictions
  } = useWorldStore();

  // The URL decides the world (a reload or a pasted link has no earlier selection in the store)
  useEffect(() => {
    if (worldId && worldId !== activeWorldId) setActiveWorld(worldId);
  }, [worldId, activeWorldId, setActiveWorld]);

  const currentPath = location.pathname;
  const currentWorldId = worldId || 'terra-incognita';

  // Count active contradictions to show a badge on the navigation rail
  const unresolvedContradictionsCount = contradictions.filter(c => !c.resolved).length;

  const navItems = [
    {
      path: `/worlds/${currentWorldId}`,
      icon: 'home',
      label: 'Home'
    },
    {
      path: `/worlds/${currentWorldId}/manuscripts`,
      icon: 'menu_book',
      label: 'Manuscripts'
    },
    {
      path: `/worlds/${currentWorldId}/world`,
      icon: 'public',
      label: 'World Ledger'
    },
    {
      path: `/worlds/${currentWorldId}/graph`,
      icon: 'bubble_chart',
      label: 'Network Graph'
    },
    {
      path: `/worlds/${currentWorldId}/timeline`,
      icon: 'timeline',
      label: 'Timeline'
    },
    {
      path: `/worlds/${currentWorldId}/contradictions`,
      icon: 'rule',
      label: 'Contradictions',
      badge: unresolvedContradictionsCount > 0 ? unresolvedContradictionsCount : undefined
    },
    {
      path: `/worlds/${currentWorldId}/assistant`,
      icon: 'chat_bubble_outline',
      label: 'AI Assistant'
    }
  ];

  const handleReturnToArchive = () => {
    setActiveWorld(null);
    navigate('/worlds');
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-void-black text-on-surface select-none">
      
      {/* 64px Left Navigation Rail */}
      <nav className="fixed left-0 top-0 h-full w-nav-rail-width bg-void-black border-r border-starlight-white/10 z-50 flex flex-col items-center py-4 justify-between select-none">
        
        {/* Brand/Logo Constellation Icon */}
        <div className="flex flex-col items-center gap-1 group cursor-pointer" onClick={handleReturnToArchive} title="Return to Archive">
          <div className="w-10 h-10 rounded-full border border-primary/30 flex items-center justify-center bg-surface-container overflow-hidden relative group-hover:border-primary transition-all duration-300">
            <span className="material-symbols-outlined text-primary text-2xl group-hover:scale-110 transition-transform font-extralight">bubble_chart</span>
          </div>
          <span className="font-label-sm text-[9px] text-on-surface-variant/40 uppercase tracking-wider group-hover:text-primary transition-colors">Orion</span>
        </div>

        {/* Primary Navigation Tabs */}
        <div className="flex-1 w-full flex flex-col gap-2 mt-8">
          {navItems.map((item) => {
            const isActive = currentPath === item.path || (item.path.includes('/manuscripts') && currentPath.includes('/manuscripts'));
            return (
              <Link 
                key={item.path} 
                to={item.path}
                className={`relative flex flex-col items-center justify-center py-4 transition-colors duration-300 w-full group ${
                  isActive 
                    ? 'text-primary bg-primary/5' 
                    : 'text-on-surface-variant/60 hover:text-primary hover:bg-white/5'
                }`}
                title={item.label}
              >
                {/* Active Indicator bar */}
                {isActive && (
                  <span className="absolute left-0 h-8 w-[2px] bg-primary shadow-[0_0_12px_rgba(254,182,141,0.6)]" />
                )}
                
                {/* Icon with hover scaling */}
                <span className={`material-symbols-outlined text-[22px] transition-transform duration-300 ${isActive ? 'fill font-light' : 'font-light group-hover:scale-110'}`}>
                  {item.icon}
                </span>

                {/* Optional Badge */}
                {item.badge !== undefined && (
                  <span className="absolute top-2 right-2 w-4 h-4 rounded-full bg-error text-void-black text-[9px] font-label-sm font-bold flex items-center justify-center border border-void-black shadow-[0_0_8px_rgba(255,180,171,0.5)]">
                    {item.badge}
                  </span>
                )}
                
                {/* Tooltip on hover */}
                <span className="opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 absolute left-full ml-4 bg-surface-container-high border border-starlight-white/10 px-3 py-1 rounded text-starlight-white text-xs font-label-sm pointer-events-none transition-all duration-200 z-50 whitespace-nowrap shadow-xl">
                  {item.label}
                </span>
              </Link>
            );
          })}
        </div>

        {/* Secondary Actions / Footer */}
        <div className="w-full flex flex-col gap-1 border-t border-starlight-white/10 pt-4 mt-auto">
          <Link 
            to={`/worlds/${currentWorldId}/assistant`}
            className="flex flex-col items-center justify-center py-4 text-on-surface-variant/60 hover:text-primary hover:bg-white/5 transition-colors duration-300 w-full group relative"
            title="Profile"
          >
            <span className="material-symbols-outlined text-[22px] font-light group-hover:scale-110 transition-transform">person_outline</span>
            <span className="opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 absolute left-full ml-4 bg-surface-container-high border border-starlight-white/10 px-3 py-1 rounded text-starlight-white text-xs font-label-sm pointer-events-none transition-all duration-200 z-50 whitespace-nowrap shadow-xl">
              Creator Profile
            </span>
          </Link>
          <button 
            onClick={handleReturnToArchive}
            className="flex flex-col items-center justify-center py-4 text-on-surface-variant/60 hover:text-primary hover:bg-white/5 transition-colors duration-300 w-full group relative"
            title="Archive Settings"
          >
            <span className="material-symbols-outlined text-[22px] font-light group-hover:rotate-45 transition-transform duration-500">settings</span>
            <span className="opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 absolute left-full ml-4 bg-surface-container-high border border-starlight-white/10 px-3 py-1 rounded text-starlight-white text-xs font-label-sm pointer-events-none transition-all duration-200 z-50 whitespace-nowrap shadow-xl">
              Archive settings
            </span>
          </button>
        </div>
      </nav>

      {/* Primary Stage */}
      <div className="flex-1 ml-nav-rail-width h-full relative flex z-10 overflow-hidden bg-void-black">
        {children}
      </div>

      {/* Contextual Side Panel (Wings) */}
      <AnimatePresence>
        {isEntityPanelOpen && activeEntityId && (
          <>
            {/* Dark blur backdrop overlay */}
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setEntityPanelOpen(false)}
              className="fixed inset-0 bg-void-black/20 backdrop-blur-[2px] z-30 ml-nav-rail-width cursor-pointer"
            />
            {/* Sidebar content container */}
            <motion.aside 
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 220 }}
              className="fixed right-0 top-0 bottom-0 w-side-panel-width z-40 h-full shrink-0"
            >
              <EntityPanel 
                entityId={activeEntityId} 
                onClose={() => setEntityPanelOpen(false)} 
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
