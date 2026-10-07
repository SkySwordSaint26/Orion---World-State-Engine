import React, { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
// import { forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide } from 'd3-force';
import {
  forceSimulation,
  forceManyBody,
  forceCenter,
  forceCollide
} from 'd3-force';
import { apiFetch } from '../api/client';

interface Node {
  id: string;
  name: string;
  type: 'character' | 'location' | 'object' | 'event';
  icon: string;
  subtype: string;
  x: number;
  y: number;
}

// interface Edge {
//   from: string;
//   to: string;
//   source?: string | Node;
//   target?: string | Node;
//   color: string;
//   dashed?: boolean;
// }
interface Edge {
  from: string;
  to: string;
  color: string;
  dashed?: boolean;
}

export const WorldGraph: React.FC = () => {
  const { worldId } = useParams<{ worldId: string }>();
  const { setActiveEntity } = useWorldStore();
  
  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState({
    character: true,
    location: true,
    object: true,
    event: true
  });
  
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  useEffect(() => {
    const fetchGraph = async () => {
      if (!worldId) return;
      try {
        const data = await apiFetch<any>(`/worlds/${worldId}/graph`);
        if (data && data.nodes && data.nodes.length > 0) {
          const fetchedNodes = data.nodes.map((ent: any) => {
            const t = (ent.type || ent.entity_type || 'character').toLowerCase();
            return {
              id: ent.id,
              name: ent.label || ent.canonical_name || 'Entity',
              type: t as Node['type'],
              icon: t === 'character' ? 'group' : t === 'location' ? 'location_on' : t === 'object' ? 'category' : 'event_note',
              subtype: t,
              x: Math.random() * 800 + 100,
              y: Math.random() * 500 + 100
            };
          });

          // const fetchedEdges = (data.edges || []).map((rel: any) => ({
          //   from: rel.source || rel.from,
          //   to: rel.target || rel.to,
          //   color: rel.type === 'ENEMY_OF' ? '#ffb4ab' : '#E6A27E',
          //   dashed: rel.type === 'ENEMY_OF'
          // }));

          // const simulation = forceSimulation(fetchedNodes)
          //   .force('charge', forceManyBody().strength(-400))
          //   .force('center', forceCenter(400, 300))
          //   .force('collide', forceCollide().radius(60))
          //   .force('link', forceLink(fetchedEdges).id((d: any) => d.id).distance(150))
          //   .stop();

          // for (let i = 0; i < 300; ++i) simulation.tick();

          // setNodes([...fetchedNodes]);
          // setEdges(fetchedEdges);

          const fetchedEdges = (data.edges || []).map((rel: any) => ({
            from: rel.source,
            to: rel.target,
            color: rel.type === 'ENEMY_OF' ? '#ffb4ab' : '#E6A27E',
            dashed: rel.type === 'ENEMY_OF'
          }));

          const simulation = forceSimulation(fetchedNodes)
            .force('charge', forceManyBody().strength(-400))
            .force('center', forceCenter(400, 300))
            .force('collide', forceCollide().radius(60))
            .stop();

          for (let i = 0; i < 300; ++i) {
            simulation.tick();
          }

          setNodes([...fetchedNodes]);
          setEdges(fetchedEdges);
        }
      } catch (err) {
        console.error("Failed to fetch graph data", err);
      }
    };
    if (worldId) fetchGraph();
  }, [worldId]);


  // Dragging state
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const dragStartPos = useRef({ x: 0, y: 0 });
  const nodeStartPos = useRef({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Hovered node state for highlighting connections
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [zoomScale, setZoomScale] = useState(1);

  const handleMouseDown = (nodeId: string, e: React.MouseEvent) => {
    e.preventDefault();
    const node = nodes.find(n => n.id === nodeId);
    if (node) {
      setDraggingNodeId(nodeId);
      dragStartPos.current = { x: e.clientX, y: e.clientY };
      nodeStartPos.current = { x: node.x, y: node.y };
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingNodeId) {
      const dx = (e.clientX - dragStartPos.current.x) / zoomScale;
      const dy = (e.clientY - dragStartPos.current.y) / zoomScale;
      
      setNodes((prev) => 
        prev.map((n) => 
          n.id === draggingNodeId 
            ? { ...n, x: nodeStartPos.current.x + dx, y: nodeStartPos.current.y + dy }
            : n
        )
      );
    }
  };

  const handleMouseUp = () => {
    setDraggingNodeId(null);
  };

  // Node styles helpers
  const getNodeColor = (type: Node['type']) => {
    switch (type) {
      case 'character': return 'border-copper-glow text-copper-glow shadow-[0_0_15px_rgba(230,162,126,0.1)]';
      case 'location': return 'border-secondary text-secondary shadow-[0_0_15px_rgba(194,198,214,0.1)]';
      case 'object': return 'border-tertiary text-tertiary shadow-[0_0_15px_rgba(200,198,197,0.1)]';
      case 'event': return 'border-error text-error shadow-[0_0_15px_rgba(255,180,171,0.1)]';
      default: return 'border-outline text-on-surface-variant';
    }
  };



  // Check if edge is active (connected to hovered node)
  const isEdgeActive = (edge: Edge) => {
    if (!hoveredNodeId) return true;
    return edge.from === hoveredNodeId || edge.to === hoveredNodeId;
  };

  // Filter nodes & edges
  const visibleNodes = nodes.filter(n => {
    const matchesFilter = filters[n.type];
    const matchesSearch = n.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          n.subtype.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const visibleNodeIds = new Set(visibleNodes.map(n => n.id));

  const visibleEdges = edges.filter(e => {
    return visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to);
  });

  const handleZoomIn = () => setZoomScale(prev => Math.min(prev + 0.15, 1.8));
  const handleZoomOut = () => setZoomScale(prev => Math.max(prev - 0.15, 0.5));
  const handleZoomFit = () => setZoomScale(1);

  return (
    <AppShell>
      <main className="flex-1 w-full h-full flex relative select-none">
        
        {/* Left Control Sidebar */}
        <aside className="w-64 bg-surface-container-low/50 backdrop-blur-sm border-r border-starlight-white/5 h-full flex flex-col z-10 shrink-0 select-none">
          <div className="p-gutter flex flex-col gap-stack-lg h-full overflow-y-auto pt-10">
            
            {/* Search */}
            <div className="relative group">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-base group-focus-within:text-primary transition-colors font-light">search</span>
              <input 
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search entities..."
                className="w-full bg-surface-container-highest/50 border-b border-starlight-white/10 border-x-0 border-t-0 px-9 py-2 font-body-md text-xs text-on-surface focus:border-primary focus:ring-0 focus:bg-surface-container-highest transition-all placeholder:text-on-surface-variant/40"
              />
            </div>

            {/* Filters */}
            <div className="flex flex-col gap-4">
              <h3 className="font-label-sm text-[10px] text-on-surface-variant uppercase tracking-widest border-b border-starlight-white/5 pb-2">Filter Network</h3>
              <div className="flex flex-col gap-2.5">
                
                {/* Characters */}
                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group text-xs font-label-sm uppercase tracking-wider">
                  <input 
                    type="checkbox"
                    checked={filters.character}
                    onChange={(e) => setFilters({ ...filters, character: e.target.checked })}
                    className="form-checkbox rounded bg-surface border-outline-variant/30 text-primary focus:ring-primary focus:ring-offset-surface-container-low w-4 h-4"
                  />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#E6A27E] shadow-[0_0_8px_rgba(230,162,126,0.5)]"></div>
                  <span className="text-on-surface group-hover:text-primary transition-colors">Characters</span>
                </label>

                {/* Locations */}
                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group text-xs font-label-sm uppercase tracking-wider">
                  <input 
                    type="checkbox"
                    checked={filters.location}
                    onChange={(e) => setFilters({ ...filters, location: e.target.checked })}
                    className="form-checkbox rounded bg-surface border-outline-variant/30 text-secondary focus:ring-secondary focus:ring-offset-surface-container-low w-4 h-4"
                  />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#c2c6d6] shadow-[0_0_8px_rgba(194,198,214,0.5)]"></div>
                  <span className="text-on-surface group-hover:text-secondary transition-colors">Locations</span>
                </label>

                {/* Objects */}
                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group text-xs font-label-sm uppercase tracking-wider">
                  <input 
                    type="checkbox"
                    checked={filters.object}
                    onChange={(e) => setFilters({ ...filters, object: e.target.checked })}
                    className="form-checkbox rounded bg-surface border-outline-variant/30 text-tertiary focus:ring-tertiary focus:ring-offset-surface-container-low w-4 h-4"
                  />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#c8c6c5] shadow-[0_0_8px_rgba(200,198,197,0.5)]"></div>
                  <span className="text-on-surface group-hover:text-tertiary transition-colors">Objects</span>
                </label>

              </div>
            </div>

            {/* Instructions */}
            <div className="mt-auto bg-surface-container-low p-4 rounded-lg border border-starlight-white/5 text-[11px] text-on-surface-variant/60 leading-relaxed font-body-md select-none">
              <span className="material-symbols-outlined text-primary text-sm font-light mr-1.5 align-middle">info</span>
              Drag nodes to customize network topology. Click any node to open its details catalog.
            </div>

          </div>
        </aside>

        {/* Network Canvas */}
        <div 
          ref={containerRef}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="flex-1 relative bg-grid overflow-hidden cursor-crosshair h-full"
        >
          {/* Top Right Floating bar */}
          <div className="absolute top-gutter right-gutter z-30 flex items-center gap-3.5 bg-surface-dim/70 backdrop-blur-md border border-starlight-white/10 rounded-full px-4 py-2 shadow-lg text-xs">
            <span className="text-on-surface-variant/80 font-label-sm uppercase tracking-wider">Loom State</span>
            <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></div>
          </div>

          {/* Draggable Graph Container */}
          <div 
            className="absolute inset-0 transition-transform duration-75 origin-center"
            style={{ transform: `scale(${zoomScale})` }}
          >
            {/* SVG Edges Layer */}
            <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(250,250,250,0.1)" />
                </marker>
              </defs>
              {visibleEdges.map((edge, idx) => {
                const fromNode = visibleNodes.find(n => n.id === edge.from);
                const toNode = visibleNodes.find(n => n.id === edge.to);

                if (!fromNode || !toNode) return null;

                const isHoveredRelated = isEdgeActive(edge);
                const opacity = hoveredNodeId ? (isHoveredRelated ? 0.8 : 0.15) : 0.4;
                const strokeWidth = hoveredNodeId && isHoveredRelated ? 2 : 1.2;

                return (
                  <line
                    key={idx}
                    x1={fromNode.x}
                    y1={fromNode.y}
                    x2={toNode.x}
                    y2={toNode.y}
                    stroke={edge.color}
                    strokeWidth={strokeWidth}
                    strokeDasharray={edge.dashed ? '4 4' : undefined}
                    opacity={opacity}
                    className="transition-all duration-300"
                  />
                );
              })}
            </svg>

            {/* Nodes Layer */}
            {visibleNodes.map((node) => {
              const isHovered = hoveredNodeId === node.id;
              const isDimmed = hoveredNodeId && hoveredNodeId !== node.id && !edges.some(edge => 
                (edge.from === node.id && edge.to === hoveredNodeId) || 
                (edge.to === node.id && edge.from === hoveredNodeId)
              );

              return (
                <div
                  key={node.id}
                  onMouseDown={(e) => handleMouseDown(node.id, e)}
                  onMouseEnter={() => setHoveredNodeId(node.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                  onClick={() => setActiveEntity(node.id)}
                  className={`absolute -translate-x-1/2 -translate-y-1/2 z-10 cursor-grab active:cursor-grabbing transition-all duration-300 ${
                    isDimmed ? 'opacity-30 scale-95' : 'opacity-100 scale-100'
                  }`}
                  style={{ left: node.x, top: node.y }}
                >
                  <div className="relative group/node">
                    
                    {/* Node Halo Ring on Hover */}
                    <div className={`absolute -inset-4 rounded-full blur-lg opacity-0 transition-opacity duration-300 pointer-events-none ${
                      isHovered ? 'opacity-25 bg-primary' : 'group-hover/node:opacity-10 bg-primary/20'
                    }`} />
                    
                    {/* Core Circle */}
                    <div className={`w-12 h-12 rounded-full bg-surface-container-high/95 border-2 flex items-center justify-center relative z-10 ${getNodeColor(node.type)} ${
                      isHovered ? 'scale-110 border-primary' : 'group-hover/node:scale-105'
                    } transition-transform duration-300`}>
                      <span className="material-symbols-outlined text-xl font-light">
                        {node.icon}
                      </span>
                      
                      {/* Sub-node pulse indicator */}
                      {node.id === 'elara-vance' && (
                        <span className="absolute -top-0.5 -right-0.5 w-3 h-3 rounded-full bg-primary border-2 border-void-black flex items-center justify-center animate-pulse" />
                      )}
                    </div>

                    {/* Label (Dynamic Positioning below) */}
                    <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 whitespace-nowrap text-center pointer-events-none select-none">
                      <p className={`font-body-md text-[11px] font-medium leading-none ${
                        isHovered ? 'text-starlight-white' : 'text-on-surface-variant'
                      }`}>{node.name}</p>
                      <p className="font-label-sm text-[8px] text-on-surface-variant/40 uppercase tracking-widest mt-0.5 leading-none">
                        {node.subtype}
                      </p>
                    </div>

                  </div>
                </div>
              );
            })}
          </div>

          {/* Canvas Zoom Controls (Bottom Right) */}
          <div className="absolute bottom-gutter right-gutter flex gap-2 z-30 select-none">
            <button 
              onClick={handleZoomIn}
              className="w-10 h-10 bg-surface-container-high/85 border border-starlight-white/10 rounded flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container"
              title="Zoom In"
            >
              <span className="material-symbols-outlined font-light">zoom_in</span>
            </button>
            <button 
              onClick={handleZoomOut}
              className="w-10 h-10 bg-surface-container-high/85 border border-starlight-white/10 rounded flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container"
              title="Zoom Out"
            >
              <span className="material-symbols-outlined font-light">zoom_out</span>
            </button>
            <button 
              onClick={handleZoomFit}
              className="w-10 h-10 bg-surface-container-high/85 border border-starlight-white/10 rounded flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container ml-1"
              title="Reset View"
            >
              <span className="material-symbols-outlined font-light">fit_screen</span>
            </button>
          </div>

        </div>

      </main>
    </AppShell>
  );
};
