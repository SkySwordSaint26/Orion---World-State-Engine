import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import {
  forceSimulation,
  forceManyBody,
  forceCenter,
  forceCollide,
} from 'd3-force';
import { apiFetch } from '../api/client';
import {
  getRelationship,
  createRelationship,
  updateRelationship,
  deleteRelationship,
  type RelationshipResponse,
} from '../api/relationships';

interface Node {
  id: string;
  name: string;
  type: 'character' | 'location' | 'object' | 'event';
  icon: string;
  subtype: string;
  degree: number;
  properties: Record<string, any>;
  x: number;
  y: number;
}

interface Edge {
  id: string;
  from: string;
  to: string;
  type: string;
  color: string;
  dashed?: boolean;
}

const COMMON_RELATIONSHIP_TYPES = [
  'ALLY_OF',
  'ENEMY_OF',
  'KNOWS',
  'FRIEND_OF',
  'LIVES_AT',
  'KEEPER_OF',
  'CAPTAIN_OF',
  'FAMILY_OF',
  'MEMBER_OF',
  'EMPLOYS',
  'WORKS_FOR',
  'RELATED_TO',
];

export const WorldGraph: React.FC = () => {
  const { worldId } = useParams<{ worldId: string }>();
  const { 
    setActiveEntity, 
    manuscripts, 
    fetchManuscriptsForWorld, 
    fetchEntitiesForWorld,
    relationshipRevision,
    notifyRelationshipsChanged
  } = useWorldStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [controlsOpen, setControlsOpen] = useState(() => window.innerWidth >= 768);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    character: true,
    location: true,
    object: true,
    event: true,
  });

  // Time-slice state: null means "latest" (§16)
  const [asOfChapter, setAsOfChapter] = useState<number | null>(null);

  // Available chapters for time slider (deduplicated by chapter number and sorted)
  const chapters = manuscripts
    .flatMap((m) => m.chapters || [])
    .filter((ch, index, self) => index === self.findIndex((c) => c.number === ch.number))
    .sort((a, b) => a.number - b.number);
  const maxChapter = chapters.length > 0 ? Math.max(...chapters.map((c) => c.number)) : 1;

  // Step handlers for scrubbing through chapters sequentially
  const handleStepPrev = () => {
    if (asOfChapter === null) {
      setAsOfChapter(maxChapter);
    } else if (asOfChapter > 1) {
      const prevChapters = chapters.filter((c) => c.number < asOfChapter);
      if (prevChapters.length > 0) {
        setAsOfChapter(prevChapters[prevChapters.length - 1].number);
      } else {
        setAsOfChapter(Math.max(1, asOfChapter - 1));
      }
    }
  };

  const handleStepNext = () => {
    if (asOfChapter === null) return;
    const nextChapters = chapters.filter((c) => c.number > asOfChapter);
    if (nextChapters.length > 0) {
      setAsOfChapter(nextChapters[0].number);
    } else {
      setAsOfChapter(null); // Step to Latest
    }
  };

  // Fetch manuscripts and entities when worldId is available
  useEffect(() => {
    if (worldId) {
      fetchManuscriptsForWorld(worldId).catch(() => {});
      fetchEntitiesForWorld(worldId).catch(() => {});
    }
  }, [worldId, fetchManuscriptsForWorld, fetchEntitiesForWorld]);

  const [nodes, setNodes] = useState<Node[]>([]);
  const nodePositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const hasInitializedLayoutRef = useRef(false);
  const graphRequestRef = useRef(0);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(false);

  // Canvas Pan & Zoom state
  const [zoomScale, setZoomScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  // Node Dragging state
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const [connectionDraft, setConnectionDraft] = useState<{ sourceId: string; x: number; y: number } | null>(null);
  const dragStartPos = useRef({ x: 0, y: 0 });
  const nodeStartPos = useRef({ x: 0, y: 0 });
  const dragDistanceRef = useRef(0);

  // Canvas Panning state
  const [isPanning, setIsPanning] = useState(false);
  const panStartPos = useRef({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Hovered node state for highlighting connections
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  // Selected edge state for relationship details drawer
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [selectedRelData, setSelectedRelData] = useState<RelationshipResponse | null>(null);
  const [loadingRel, setLoadingRel] = useState(false);
  const [relActionError, setRelActionError] = useState<string | null>(null);

  // Add Relationship Modal state
  const [isAddRelOpen, setIsAddRelOpen] = useState(false);
  const [newRelSource, setNewRelSource] = useState('');
  const [newRelTarget, setNewRelTarget] = useState('');
  const [newRelType, setNewRelType] = useState('ALLY_OF');
  const [customNewRelType, setCustomNewRelType] = useState('');
  const [newRelChapterId, setNewRelChapterId] = useState('');
  const [submittingRel, setSubmittingRel] = useState(false);

  // Edit Relationship Type state
  const [isEditingRelType, setIsEditingRelType] = useState(false);
  const [editRelType, setEditRelType] = useState('');
  const [customEditRelType, setCustomEditRelType] = useState('');
  const [editRelChapterId, setEditRelChapterId] = useState('');
  const [updatingRel, setUpdatingRel] = useState(false);

  const fetchGraph = useCallback(async () => {
    if (!worldId) return;
    const requestId = ++graphRequestRef.current;
    setLoading(true);
    setGraphError(null);
    try {
      const query = asOfChapter !== null ? `?as_of_chapter=${asOfChapter}` : '';
      const data = await apiFetch<any>(`/worlds/${worldId}/graph${query}`);
      if (requestId !== graphRequestRef.current) return;
      if (data && data.nodes) {
        const containerW = containerRef.current?.clientWidth || 900;
        const containerH = containerRef.current?.clientHeight || 600;
        const centerX = containerW / 2;
        const centerY = containerH / 2;

        const previousPositions = nodePositionsRef.current;
        const fetchedNodes: Node[] = data.nodes.map((ent: any, index: number) => {
          const t = (ent.type || ent.entity_type || 'character').toLowerCase();
          const previous = previousPositions.get(ent.id);
          const angle = (index / Math.max(data.nodes.length, 1)) * Math.PI * 2;
          return {
            id: ent.id,
            name: ent.label || ent.canonical_name || 'Entity',
            type: t as Node['type'],
            icon:
              t === 'character'
                ? 'group'
                : t === 'location'
                ? 'location_on'
                : t === 'object'
                ? 'category'
                : 'event_note',
            subtype: t,
            degree: ent.degree || 0,
            properties: ent.properties || {},
            x: previous?.x ?? centerX + Math.cos(angle) * Math.min(containerW, 460) * 0.28,
            y: previous?.y ?? centerY + Math.sin(angle) * Math.min(containerH, 360) * 0.28,
          };
        });

        const fetchedEdges: Edge[] = (data.edges || []).map((rel: any) => ({
          id: rel.id,
          from: rel.source,
          to: rel.target,
          type: rel.type || 'RELATED_TO',
          color: rel.type === 'ENEMY_OF' ? '#ffb4ab' : '#E6A27E',
          dashed: rel.type === 'ENEMY_OF',
        }));

        if (!hasInitializedLayoutRef.current && fetchedNodes.length > 0) {
          const simulation = forceSimulation(fetchedNodes)
            .force('charge', forceManyBody().strength(-450))
            .force('center', forceCenter(centerX, centerY))
            .force('collide', forceCollide().radius(70))
            .stop();

          for (let i = 0; i < 300; ++i) {
            simulation.tick();
          }
          hasInitializedLayoutRef.current = true;
        }

        fetchedNodes.forEach((node) => nodePositionsRef.current.set(node.id, { x: node.x, y: node.y }));
        setNodes([...fetchedNodes]);
        setEdges(fetchedEdges);
      }
    } catch (err) {
      if (requestId === graphRequestRef.current) setGraphError(err instanceof Error ? err.message : 'Could not load graph.');
    } finally {
      if (requestId === graphRequestRef.current) setLoading(false);
    }
  }, [worldId, asOfChapter]);

  useEffect(() => {
    nodePositionsRef.current.clear();
    hasInitializedLayoutRef.current = false;
    setNodes([]);
    setEdges([]);
  }, [worldId]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph, relationshipRevision]);

  // Non-passive wheel listener for Ctrl + Scroll zoom & trackpad pinch
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const rect = container.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const zoomFactor = e.deltaY < 0 ? 1.12 : 0.89;
        setZoomScale((prevScale) => {
          const newScale = Math.min(Math.max(prevScale * zoomFactor, 0.25), 3.0);
          setPan((prevPan) => ({
            x: mouseX - ((mouseX - prevPan.x) / prevScale) * newScale,
            y: mouseY - ((mouseY - prevPan.y) / prevScale) * newScale,
          }));
          return newScale;
        });
      } else {
        // Standard wheel pans canvas
        setPan((prev) => ({
          x: prev.x - e.deltaX,
          y: prev.y - e.deltaY,
        }));
      }
    };

    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      container.removeEventListener('wheel', handleWheel);
    };
  }, []);

  // Keyboard navigation (+, -, 0, Arrow keys)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) {
        return;
      }
      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        setZoomScale((z) => Math.min(z * 1.15, 3.0));
      } else if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        setZoomScale((z) => Math.max(z / 1.15, 0.25));
      } else if (e.key === '0' || e.key === 'Escape') {
        e.preventDefault();
        setZoomScale(1);
        setPan({ x: 0, y: 0 });
        if (e.key === 'Escape') {
          setSelectedEdgeId(null);
          setSelectedRelData(null);
          setIsAddRelOpen(false);
          setConnectionDraft(null);
        }
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setPan((p) => ({ ...p, x: p.x + 40 }));
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        setPan((p) => ({ ...p, x: p.x - 40 }));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setPan((p) => ({ ...p, y: p.y + 40 }));
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setPan((p) => ({ ...p, y: p.y - 40 }));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Node Dragging Handlers
  const handleNodeMouseDown = (nodeId: string, e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation(); // Prevent canvas pan
    e.preventDefault();
    const node = nodes.find((n) => n.id === nodeId);
    if (node) {
      setDraggingNodeId(nodeId);
      dragDistanceRef.current = 0;
      dragStartPos.current = { x: e.clientX, y: e.clientY };
      nodeStartPos.current = { x: node.x, y: node.y };
    }
  };

  const handleCanvasMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsPanning(true);
    panStartPos.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (connectionDraft && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setConnectionDraft({ ...connectionDraft, x: (e.clientX - rect.left - pan.x) / zoomScale, y: (e.clientY - rect.top - pan.y) / zoomScale });
    } else if (draggingNodeId) {
      const dx = (e.clientX - dragStartPos.current.x) / zoomScale;
      const dy = (e.clientY - dragStartPos.current.y) / zoomScale;
      dragDistanceRef.current += Math.hypot(e.movementX || 0, e.movementY || 0);

      setNodes((prev) =>
        prev.map((n) => {
          if (n.id !== draggingNodeId) return n;
          const updated = { ...n, x: nodeStartPos.current.x + dx, y: nodeStartPos.current.y + dy };
          nodePositionsRef.current.set(updated.id, { x: updated.x, y: updated.y });
          return updated;
        })
      );
    } else if (isPanning) {
      setPan({
        x: e.clientX - panStartPos.current.x,
        y: e.clientY - panStartPos.current.y,
      });
    }
  };

  const handleMouseUp = (event: React.MouseEvent) => {
    if (connectionDraft) {
      const targetId = (event.target as Element).closest<HTMLElement>('[data-node-id]')?.dataset.nodeId;
      if (event.type !== 'mouseleave' && targetId && targetId !== connectionDraft.sourceId) {
        setNewRelSource(connectionDraft.sourceId);
        setNewRelTarget(targetId);
        setNewRelType('ALLY_OF');
        setCustomNewRelType('');
        setNewRelChapterId('');
        setIsAddRelOpen(true);
      }
      dragDistanceRef.current = 10;
      setConnectionDraft(null);
    }
    setDraggingNodeId(null);
    setIsPanning(false);
  };

  // Node Click: Only open info tab if NOT dragging (> 5px traveled)
  const handleNodeClick = (nodeId: string) => {
    if (dragDistanceRef.current > 5) {
      return; // Was dragging, don't open info tab
    }
    setSelectedEdgeId(null);
    setSelectedRelData(null);
    setActiveEntity(nodeId);
  };

  // Edge Click: Load relationship version history
  const handleEdgeClick = async (e: React.MouseEvent, edge: Edge) => {
    e.stopPropagation();
    if (!worldId) return;
    setActiveEntity(null);
    setSelectedEdgeId(edge.id);
    setLoadingRel(true);
    setRelActionError(null);
    setIsEditingRelType(false);
    try {
      const data = await getRelationship(worldId, edge.id);
      setSelectedRelData(data);
      const curType = data.current_version?.relationship_type || edge.type;
      if (COMMON_RELATIONSHIP_TYPES.includes(curType)) {
        setEditRelType(curType);
        setCustomEditRelType('');
      } else {
        setEditRelType('OTHER');
        setCustomEditRelType(curType);
      }
      setEditRelChapterId(data.current_version?.chapter_id || '');
    } catch (err: any) {
      console.error('Failed to fetch relationship details:', err);
      setRelActionError(err?.message || 'Failed to fetch relationship details');
    } finally {
      setLoadingRel(false);
    }
  };

  // Update relationship type (§14.4)
  const handleUpdateRelType = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!worldId || !selectedEdgeId) return;
    const resolvedType = editRelType === 'OTHER' ? customEditRelType.trim() : editRelType.trim();
    if (!resolvedType) {
      setRelActionError('Please enter a relationship type');
      return;
    }

    setUpdatingRel(true);
    setRelActionError(null);
    try {
      const updated = await updateRelationship(worldId, selectedEdgeId, {
        relationship_type: resolvedType.toUpperCase(),
        chapter_id: editRelChapterId || null,
      });
      setSelectedRelData(updated);
      setIsEditingRelType(false);
      notifyRelationshipsChanged();
    } catch (err: any) {
      console.error('Failed to update relationship:', err);
      setRelActionError(err?.message || 'Failed to update relationship');
    } finally {
      setUpdatingRel(false);
    }
  };

  // Delete relationship (§14.5)
  const handleDeleteRel = async () => {
    if (!worldId || !selectedEdgeId) return;
    if (!confirm('Are you sure you want to delete this relationship and all historical versions?')) return;
    try {
      await deleteRelationship(worldId, selectedEdgeId);
      setSelectedEdgeId(null);
      setSelectedRelData(null);
      notifyRelationshipsChanged();
    } catch (err: any) {
      console.error('Failed to delete relationship:', err);
      setRelActionError(err?.message || 'Failed to delete relationship');
    }
  };

  // Create relationship (§14.3)
  const handleCreateRelationship = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!worldId || !newRelSource || !newRelTarget) return;
    if (newRelSource === newRelTarget) {
      alert('Source and target entities must be different.');
      return;
    }
    const resolvedType = newRelType === 'OTHER' ? customNewRelType.trim() : newRelType.trim();
    if (!resolvedType) {
      alert('Please specify a relationship type.');
      return;
    }

    setSubmittingRel(true);
    try {
      await createRelationship(worldId, {
        source_entity_id: newRelSource,
        target_entity_id: newRelTarget,
        relationship_type: resolvedType.toUpperCase(),
        chapter_id: newRelChapterId || null,
      });
      setIsAddRelOpen(false);
      notifyRelationshipsChanged();
    } catch (err: any) {
      console.error('Failed to create relationship:', err);
      alert(err?.message || 'Failed to create relationship');
    } finally {
      setSubmittingRel(false);
    }
  };

  const getNodeColor = (type: Node['type']) => {
    switch (type) {
      case 'character':
        return 'border-copper-glow text-copper-glow shadow-[0_0_15px_rgba(230,162,126,0.1)]';
      case 'location':
        return 'border-secondary text-secondary shadow-[0_0_15px_rgba(194,198,214,0.1)]';
      case 'object':
        return 'border-tertiary text-tertiary shadow-[0_0_15px_rgba(200,198,197,0.1)]';
      case 'event':
        return 'border-error text-error shadow-[0_0_15px_rgba(255,180,171,0.1)]';
      default:
        return 'border-outline text-on-surface-variant';
    }
  };

  const isEdgeActive = (edge: Edge) => {
    if (selectedEdgeId === edge.id) return true;
    if (!hoveredNodeId) return true;
    return edge.from === hoveredNodeId || edge.to === hoveredNodeId;
  };

  // Filter nodes & edges
  const visibleNodes = nodes.filter((n) => {
    const matchesFilter = filters[n.type] ?? true;
    const matchesSearch =
      n.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      n.subtype.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));

  const visibleEdges = edges.filter((e) => {
    return visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to);
  });

  const handleZoomIn = () => setZoomScale((prev) => Math.min(prev * 1.15, 3.0));
  const handleZoomOut = () => setZoomScale((prev) => Math.max(prev / 1.15, 0.25));
  const handleZoomFit = () => {
    if (!visibleNodes.length || !containerRef.current) {
      setZoomScale(1);
      setPan({ x: 0, y: 0 });
      return;
    }
    const bounds = visibleNodes.reduce(
      (acc, node) => ({
        minX: Math.min(acc.minX, node.x),
        maxX: Math.max(acc.maxX, node.x),
        minY: Math.min(acc.minY, node.y),
        maxY: Math.max(acc.maxY, node.y),
      }),
      { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity },
    );
    const width = Math.max(bounds.maxX - bounds.minX + 160, 240);
    const height = Math.max(bounds.maxY - bounds.minY + 160, 240);
    const scale = Math.min(
      1,
      Math.max(0.25, Math.min(containerRef.current.clientWidth / width, containerRef.current.clientHeight / height)),
    );
    setZoomScale(scale);
    setPan({
      x: containerRef.current.clientWidth / 2 - ((bounds.minX + bounds.maxX) / 2) * scale,
      y: containerRef.current.clientHeight / 2 - ((bounds.minY + bounds.maxY) / 2) * scale,
    });
  };

  return (
    <AppShell>
      <header className="absolute inset-x-0 top-0 h-14 bg-surface-dim/85 backdrop-blur-md border-b border-starlight-white/5 z-40 flex items-center justify-between px-6 pointer-events-none">
        <div className="flex items-center gap-4">
          <span className="font-headline-md text-headline-md text-primary">World Graph</span>
          <span className="text-on-surface-variant/50">/</span>
          <span className="font-label-sm uppercase tracking-widest text-on-surface-variant/70">Filament cartography</span>
        </div>
        <div className="pointer-events-auto flex items-center gap-4"><span className="hidden text-xs text-on-surface-variant/60 sm:inline">{visibleNodes.length} entities</span><button className="studio-secondary" aria-expanded={controlsOpen} onClick={() => setControlsOpen(value => !value)}>Graph controls</button></div>
      </header>

      <main className="flex-1 w-full h-full pt-14 flex relative select-none overflow-hidden">
        {/* Left Control Sidebar */}
        {controlsOpen && <aside aria-label="Graph controls" className="graph-sidebar flex h-full flex-col !p-0">
          <div className="p-gutter flex flex-col gap-5 h-full overflow-y-auto pt-6">
            {/* Search */}
            <div className="relative group">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-base group-focus-within:text-primary transition-colors font-light">
                search
              </span>
              <input
                type="text"
                placeholder="Search entities..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-surface-container-high/60 border border-outline-variant/30 rounded-lg pl-9 pr-3 py-1.5 text-xs text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:border-primary/50 transition-colors"
              />
            </div>

            {/* Narrative Time-Slice Scrubber (§16) */}
            {chapters.length > 0 && (
              <div className="flex flex-col gap-3 p-3.5 rounded-xl bg-surface-container/60 border border-starlight-white/10 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="font-label-sm text-[10px] text-primary uppercase tracking-widest font-semibold flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm">history</span>
                    Time Slice
                  </span>
                  <span className="text-[11px] font-bold text-starlight-white bg-primary/10 border border-primary/20 px-2 py-0.5 rounded flex items-center gap-1.5">
                    {asOfChapter !== null ? (
                      `End of Ch. ${asOfChapter}`
                    ) : (
                      <>
                        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                        <span>Latest (Now)</span>
                      </>
                    )}
                  </span>
                </div>

                {/* Scrubber & Step Controls */}
                <div className="flex flex-col gap-2 mt-1">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleStepPrev}
                      disabled={asOfChapter === 1}
                      title="Step to previous chapter"
                      className="p-1 rounded bg-surface-container-high/60 hover:bg-surface-container-highest text-on-surface-variant hover:text-white disabled:opacity-30 disabled:pointer-events-none transition-colors border border-starlight-white/5"
                    >
                      <span className="material-symbols-outlined text-xs">chevron_left</span>
                    </button>

                    <input
                      type="range"
                      min="1"
                      max={maxChapter + 1}
                      step="1"
                      value={asOfChapter === null ? maxChapter + 1 : asOfChapter}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        if (val > maxChapter) {
                          setAsOfChapter(null); // Latest
                        } else {
                          setAsOfChapter(val);
                        }
                      }}
                      className="flex-1 accent-primary h-1.5 bg-surface-container-highest rounded-lg cursor-pointer"
                    />

                    <button
                      onClick={handleStepNext}
                      disabled={asOfChapter === null}
                      title="Step to next chapter"
                      className="p-1 rounded bg-surface-container-high/60 hover:bg-surface-container-highest text-on-surface-variant hover:text-white disabled:opacity-30 disabled:pointer-events-none transition-colors border border-starlight-white/5"
                    >
                      <span className="material-symbols-outlined text-xs">chevron_right</span>
                    </button>
                  </div>

                  <div className="flex justify-between items-center text-[10px] text-on-surface-variant/60 font-mono px-0.5">
                    <span>Ch 1</span>
                    {maxChapter > 1 && <span>Ch {maxChapter}</span>}
                    <span className="text-primary font-bold">Latest</span>
                  </div>

                  {/* Every Chapter Pill + Latest Button */}
                  <div className="flex flex-wrap gap-1.5 mt-1.5 max-h-36 overflow-y-auto p-0.5">
                    {chapters.map((ch) => {
                      const isSelected = asOfChapter === ch.number;
                      return (
                        <button
                          key={ch.id || ch.number}
                          onClick={() => setAsOfChapter(ch.number)}
                          title={ch.title ? `Ch. ${ch.number}: ${ch.title}` : `Chapter ${ch.number}`}
                          className={`py-1 px-2.5 rounded-md text-[11px] font-mono transition-all border ${
                            isSelected
                              ? 'bg-primary/20 text-primary border-primary/50 font-bold shadow-sm ring-1 ring-primary/30'
                              : 'bg-surface-container-high/60 text-on-surface-variant/80 border-starlight-white/5 hover:border-starlight-white/20 hover:text-white hover:bg-surface-container-highest/80'
                          }`}
                        >
                          Ch. {ch.number}
                        </button>
                      );
                    })}
                    <button
                      onClick={() => setAsOfChapter(null)}
                      title="Latest World State"
                      className={`py-1 px-3 rounded-md text-[11px] font-mono transition-all border flex items-center gap-1.5 ${
                        asOfChapter === null
                          ? 'bg-primary/20 text-primary border-primary/50 font-bold shadow-sm ring-1 ring-primary/30'
                          : 'bg-surface-container-high/60 text-on-surface-variant/80 border-starlight-white/5 hover:border-starlight-white/20 hover:text-white hover:bg-surface-container-highest/80'
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${asOfChapter === null ? 'bg-primary animate-pulse' : 'bg-on-surface-variant/40'}`} />
                      Latest
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Add Relationship Action Button */}
            <button
              onClick={() => {
                setIsAddRelOpen(true);
                if (nodes.length >= 2) {
                  setNewRelSource(nodes[0].id);
                  setNewRelTarget(nodes[1].id);
                } else if (nodes.length === 1) {
                  setNewRelSource(nodes[0].id);
                  setNewRelTarget('');
                }
                setNewRelType('ALLY_OF');
                setCustomNewRelType('');
                setNewRelChapterId('');
              }}
              className="w-full py-2 px-3 rounded-lg bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 text-xs font-semibold flex items-center justify-center gap-2 transition-colors shadow-sm"
            >
              <span className="material-symbols-outlined text-sm">add_link</span>
              Add Relationship
            </button>
            <p className="text-[11px] text-on-surface-variant/60 leading-relaxed">Drag the arrow handle on a node onto another node to create a relationship. Press Esc to cancel.</p>

            {/* Filters */}
            <div className="flex flex-col gap-3">
              <h3 className="font-label-sm text-[10px] text-on-surface-variant uppercase tracking-widest border-b border-starlight-white/5 pb-2">
                Filter Network
              </h3>
              <div className="flex flex-col gap-2">
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

                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group text-xs font-label-sm uppercase tracking-wider">
                  <input
                    type="checkbox"
                    checked={filters.event}
                    onChange={(e) => setFilters({ ...filters, event: e.target.checked })}
                    className="form-checkbox rounded bg-surface border-outline-variant/30 text-primary focus:ring-primary focus:ring-offset-surface-container-low w-4 h-4"
                  />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#ffb4ab] shadow-[0_0_8px_rgba(255,180,171,0.5)]"></div>
                  <span className="text-on-surface group-hover:text-error transition-colors">Events</span>
                </label>
              </div>
            </div>

            {/* Controls Guide */}
            <details className="mt-auto bg-surface-container-low rounded-lg border border-starlight-white/5 text-[11px] text-on-surface-variant/70 leading-relaxed font-body-md select-none">
              <summary className="cursor-pointer list-none p-3.5 font-semibold text-primary flex items-center gap-1 focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary">
                <span className="material-symbols-outlined text-sm">keyboard</span>
                Canvas controls
                <span className="material-symbols-outlined text-sm ml-auto">expand_more</span>
              </summary>
              <div className="px-3.5 pb-3.5 space-y-1.5">
              <div className="font-semibold text-primary flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">info</span>
                Shortcuts
              </div>
              <div>• <b>Ctrl + Scroll</b>: Zoom at cursor</div>
              <div>• <b>Drag Canvas</b>: Pan view</div>
              <div>• <b>Click Edge / Badge</b>: Inspect relationship</div>
              <div>• <b>Single Click Node</b>: Inspect entity</div>
              <div>• <b>Drag Node</b>: Rearrange layout</div>
              <div>• <b>+ / - / 0</b>: Zoom & reset</div>
              </div>
            </details>
          </div>
        </aside>}

        {/* Network Canvas */}
        <div
          ref={containerRef}
          onMouseDown={handleCanvasMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className={`min-w-0 flex-1 relative bg-grid overflow-hidden h-full ${
            isPanning ? 'cursor-grabbing' : 'cursor-grab'
          }`}
        >
          {graphError && <div role="alert" className="absolute inset-x-5 top-20 z-40 rounded border border-error/30 bg-surface-container p-4 text-sm text-error">{graphError}<button className="ml-4 underline" onClick={fetchGraph}>Retry</button></div>}
          {/* Top Right Floating bar */}
          <div className="absolute top-gutter right-gutter z-30 flex items-center gap-3.5 bg-surface-dim/80 backdrop-blur-md border border-starlight-white/10 rounded-full px-4 py-2 shadow-lg text-xs pointer-events-auto">
            <span className="text-on-surface-variant/80 font-label-sm uppercase tracking-wider">
              {asOfChapter !== null ? `Time Slice: Ch. ${asOfChapter}` : 'Chronicle Graph'}
            </span>
            <div className={`w-2 h-2 rounded-full ${loading ? 'bg-copper-glow animate-spin' : 'bg-primary animate-pulse'}`}></div>
          </div>

          {loading && (
            <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none">
              <div className="glass-panel rounded-xl px-4 py-3 text-xs text-primary flex items-center gap-2">
                <span className="material-symbols-outlined animate-spin text-base">progress_activity</span>
                Loading network…
              </div>
            </div>
          )}

          {!loading && nodes.length === 0 && (
            <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none p-6">
              <div className="glass-panel rounded-xl max-w-sm text-center px-6 py-8">
                <span className="material-symbols-outlined text-3xl text-primary/70 mb-3">bubble_chart</span>
                <h2 className="font-headline-md text-headline-md text-starlight-white">No relationships yet</h2>
                <p className="text-sm text-on-surface-variant/70 mt-2">Add entities and relationships to begin mapping this world.</p>
              </div>
            </div>
          )}

          {!loading && nodes.length > 0 && visibleNodes.length === 0 && (
            <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none p-6">
              <div className="glass-panel rounded-xl max-w-sm text-center px-6 py-8 pointer-events-auto">
                <span className="material-symbols-outlined text-3xl text-on-surface-variant/70 mb-3">filter_alt_off</span>
                <h2 className="font-headline-md text-headline-md text-starlight-white">No matching entities</h2>
                <p className="text-sm text-on-surface-variant/70 mt-2">Adjust the search or entity filters to restore the network.</p>
                <button onClick={() => { setSearchQuery(''); setFilters({ character: true, location: true, object: true, event: true }); }} className="mt-4 text-xs text-primary hover:underline">Reset filters</button>
              </div>
            </div>
          )}

          {/* Unified Pan/Zoom Graph Container */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoomScale})`,
              transformOrigin: '0 0',
            }}
          >
            {/* SVG Edges Layer with overflow: visible to eliminate cutoff */}
            <svg
              className="absolute inset-0 w-full h-full pointer-events-none z-0 overflow-visible"
              style={{ overflow: 'visible' }}
            >
              <defs>
                <marker id="arrow-draft" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#feb68d" />
                </marker>
                <marker
                  id="arrow"
                  viewBox="0 0 10 10"
                  refX="28"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(230,162,126,0.6)" />
                </marker>
                <marker
                  id="arrow-selected"
                  viewBox="0 0 10 10"
                  refX="28"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#E6A27E" />
                </marker>
              </defs>

              {connectionDraft && (() => {
                const source = nodes.find(node => node.id === connectionDraft.sourceId);
                return source ? <line x1={source.x} y1={source.y} x2={connectionDraft.x} y2={connectionDraft.y} stroke="#feb68d" strokeWidth={2} strokeDasharray="6 4" markerEnd="url(#arrow-draft)" /> : null;
              })()}
              {/* Edge Lines & Interactive Hit Areas */}
              {visibleEdges.map((edge) => {
                const fromNode = visibleNodes.find((n) => n.id === edge.from);
                const toNode = visibleNodes.find((n) => n.id === edge.to);

                if (!fromNode || !toNode) return null;

                const isHoveredRelated = isEdgeActive(edge);
                const isSelected = selectedEdgeId === edge.id;
                const opacity = isSelected ? 1 : hoveredNodeId ? (isHoveredRelated ? 0.9 : 0.15) : 0.45;
                const strokeWidth = isSelected ? 2.8 : hoveredNodeId && isHoveredRelated ? 2.2 : 1.4;

                const midX = (fromNode.x + toNode.x) / 2;
                const midY = (fromNode.y + toNode.y) / 2;
                const badgeWidth = Math.max(edge.type.length * 5.2 + 14, 52);

                return (
                  <g
                    key={edge.id}
                    className="cursor-pointer pointer-events-auto"
                    onClick={(e) => handleEdgeClick(e, edge)}
                  >
                    {/* Invisible fat line for easier hovering & clicking */}
                    <line
                      x1={fromNode.x}
                      y1={fromNode.y}
                      x2={toNode.x}
                      y2={toNode.y}
                      stroke="transparent"
                      strokeWidth={18}
                    />

                    {/* Visible line */}
                    <line
                      x1={fromNode.x}
                      y1={fromNode.y}
                      x2={toNode.x}
                      y2={toNode.y}
                      stroke={isSelected ? '#E6A27E' : edge.color}
                      strokeWidth={strokeWidth}
                      strokeDasharray={edge.dashed ? '4 4' : undefined}
                      opacity={opacity}
                      markerEnd={isSelected ? 'url(#arrow-selected)' : 'url(#arrow)'}
                      className="transition-all duration-200"
                    />

                    {/* Midpoint Label Badge */}
                    <g transform={`translate(${midX}, ${midY})`}>
                      <rect
                        x={-(badgeWidth / 2)}
                        y={-9}
                        width={badgeWidth}
                        height={18}
                        rx={4}
                        fill="#181c20"
                        stroke={
                          isSelected
                            ? '#E6A27E'
                            : hoveredNodeId && isHoveredRelated
                            ? edge.color
                            : 'rgba(255,255,255,0.18)'
                        }
                        strokeWidth={isSelected ? 1.8 : 1}
                        opacity={hoveredNodeId ? (isHoveredRelated ? 1 : 0.25) : 0.9}
                      />
                      <text
                        x={0}
                        y={3.5}
                        textAnchor="middle"
                        fill={isSelected ? '#E6A27E' : hoveredNodeId && isHoveredRelated ? '#ffffff' : '#c2c6d6'}
                        fontSize="8.5px"
                        fontFamily="ui-monospace, monospace"
                        fontWeight="600"
                        letterSpacing="0.04em"
                        opacity={hoveredNodeId ? (isHoveredRelated ? 1 : 0.3) : 0.95}
                      >
                        {edge.type.replace(/_/g, ' ')}
                      </text>
                    </g>
                  </g>
                );
              })}
            </svg>

            {/* Nodes Layer */}
            {visibleNodes.map((node) => {
              const isHovered = hoveredNodeId === node.id;
              const isDimmed =
                hoveredNodeId &&
                hoveredNodeId !== node.id &&
                !edges.some(
                  (edge) =>
                    (edge.from === node.id && edge.to === hoveredNodeId) ||
                    (edge.to === node.id && edge.from === hoveredNodeId)
                );

              return (
                <div
                  key={node.id}
                  data-node-id={node.id}
                  onMouseDown={(e) => handleNodeMouseDown(node.id, e)}
                  onMouseEnter={() => setHoveredNodeId(node.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                  onClick={() => handleNodeClick(node.id)}
                  tabIndex={0}
                  role="button"
                  aria-label={`${node.name}, ${node.type}, ${node.degree} connections`}
                  onKeyDown={(e) => {
                    if (e.target !== e.currentTarget) return;
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleNodeClick(node.id);
                    }
                  }}
                  className={`absolute -translate-x-1/2 -translate-y-1/2 z-10 pointer-events-auto cursor-grab active:cursor-grabbing transition-opacity duration-200 select-none ${
                    isDimmed ? 'opacity-25 scale-95' : 'opacity-100 scale-100'
                  }`}
                  style={{ left: node.x, top: node.y }}
                >
                  <div className="relative group/node">
                    {/* Node Halo Ring on Hover */}
                    <div
                      className={`absolute -inset-4 rounded-full blur-lg opacity-0 transition-opacity duration-300 pointer-events-none ${
                        isHovered ? 'opacity-30 bg-primary' : 'group-hover/node:opacity-10 bg-primary/20'
                      }`}
                    />

                    {/* Core Circle */}
                    <div
                      className={`w-12 h-12 rounded-full bg-surface-container-high/95 border-2 flex items-center justify-center relative z-10 ${getNodeColor(
                        node.type
                      )} ${isHovered ? 'scale-110 border-primary' : 'group-hover/node:scale-105'} transition-transform duration-200`}
                    >
                      <span className="material-symbols-outlined text-xl font-light">{node.icon}</span>

                      {/* Degree Badge */}
                      {node.degree > 0 && (
                        <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-surface-container-highest border border-starlight-white/20 text-[9px] text-primary flex items-center justify-center font-bold">
                          {node.degree}
                        </span>
                      )}
                    </div>

                    <button
                      aria-label={`Drag relationship from ${node.name}`}
                      title="Drag onto another node to create a relationship"
                      onMouseDown={event => {
                        event.stopPropagation();
                        event.preventDefault();
                        if (event.button !== 0) return;
                        dragDistanceRef.current = 10;
                        setConnectionDraft({ sourceId: node.id, x: node.x + 36, y: node.y });
                      }}
                      onClick={event => event.stopPropagation()}
                      className="absolute -right-5 top-3 z-20 w-5 h-5 rounded-full bg-primary text-void-black border border-primary flex items-center justify-center cursor-crosshair hover:scale-110"
                    ><span className="material-symbols-outlined text-sm">arrow_forward</span></button>

                    {/* Label */}
                    <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 whitespace-nowrap text-center pointer-events-none select-none">
                      <p
                        className={`font-body-md text-[11px] font-medium leading-none ${
                          isHovered ? 'text-starlight-white' : 'text-on-surface-variant'
                        }`}
                      >
                        {node.name}
                      </p>
                      <p className="font-label-sm text-[8px] text-on-surface-variant/40 uppercase tracking-widest mt-0.5 leading-none">
                        {node.subtype}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Canvas Zoom & Pan Navigation Controls (Bottom Right) */}
          <div className="absolute bottom-gutter right-gutter flex items-center gap-2 z-30 select-none">
            <button
              onClick={handleZoomIn}
              aria-label="Zoom In (+)"
              className="w-10 h-10 bg-surface-container-high/90 border border-starlight-white/10 rounded-lg flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container"
              title="Zoom In (+)"
            >
              <span className="material-symbols-outlined font-light">zoom_in</span>
            </button>
            <button
              onClick={handleZoomOut}
              aria-label="Zoom Out (-)"
              className="w-10 h-10 bg-surface-container-high/90 border border-starlight-white/10 rounded-lg flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container"
              title="Zoom Out (-)"
            >
              <span className="material-symbols-outlined font-light">zoom_out</span>
            </button>
            <button
              onClick={handleZoomFit}
              className="w-10 h-10 bg-surface-container-high/90 border border-starlight-white/10 rounded-lg flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container ml-1"
              title="Reset View (0)"
            >
              <span className="material-symbols-outlined font-light">fit_screen</span>
            </button>
          </div>
        </div>

        {/* Right-Side Relationship Details & Version History Drawer */}
        {selectedEdgeId && (
          <aside className="graph-relationship flex h-full shrink-0 flex-col overflow-y-auto border-l border-white/5 bg-surface-container-low">
            {/* Header */}
            <div className="p-5 border-b border-starlight-white/10 flex items-center justify-between bg-surface-container-high/40">
              <div>
                <span className="text-[10px] uppercase tracking-wider text-primary font-semibold block">
                  Relationship Chronicle
                </span>
                <h3 className="text-sm font-bold text-starlight-white mt-0.5">
                  {selectedRelData
                    ? `${selectedRelData.source_name} → ${selectedRelData.target_name}`
                    : 'Loading Edge...'}
                </h3>
              </div>
              <button
                onClick={() => {
                  setSelectedEdgeId(null);
                  setSelectedRelData(null);
                }}
                className="w-7 h-7 rounded-lg hover:bg-white/10 flex items-center justify-center text-on-surface-variant hover:text-starlight-white transition-colors"
                title="Close"
              >
                <span className="material-symbols-outlined text-base">close</span>
              </button>
            </div>

            {/* Content */}
            <div className="p-5 space-y-6 flex-1">
              {loadingRel ? (
                <div className="flex items-center justify-center py-12 text-primary">
                  <span className="material-symbols-outlined animate-spin text-2xl">progress_activity</span>
                </div>
              ) : selectedRelData ? (
                <>
                  {relActionError && (
                    <div className="p-3 rounded-lg bg-error/10 border border-error/30 text-error text-xs">
                      {relActionError}
                    </div>
                  )}

                  {/* Current Active Status Card */}
                  <div className="p-4 rounded-xl bg-surface-container/70 border border-starlight-white/10 space-y-2">
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant/70 font-semibold block">
                      Active Narrative Status
                    </span>
                    <div className="flex items-center justify-between">
                      <span className="text-base font-bold text-starlight-white font-mono">
                        {selectedRelData.current_version?.relationship_type || 'NONE'}
                      </span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-semibold uppercase ${
                          selectedRelData.current_version?.status === 'ACTIVE'
                            ? 'bg-primary/20 text-primary border border-primary/30'
                            : 'bg-surface-container-highest text-on-surface-variant'
                        }`}
                      >
                        {selectedRelData.current_version?.status || 'INACTIVE'}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs text-on-surface-variant/80 pt-1 border-t border-starlight-white/5">
                      <span>Established In:</span>
                      <span className="font-medium text-starlight-white">
                        {selectedRelData.current_version?.chapter_number !== null &&
                        selectedRelData.current_version?.chapter_number !== undefined
                          ? `Chapter ${selectedRelData.current_version.chapter_number}`
                          : 'Universal (No Chapter)'}
                      </span>
                    </div>
                  </div>

                  {/* Update Relationship Type Section */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold">
                        Change Relationship Type
                      </span>
                      <button
                        onClick={() => setIsEditingRelType(!isEditingRelType)}
                        className="text-xs text-primary hover:underline flex items-center gap-1"
                      >
                        <span className="material-symbols-outlined text-xs">
                          {isEditingRelType ? 'expand_less' : 'edit'}
                        </span>
                        {isEditingRelType ? 'Cancel' : 'Update Type'}
                      </button>
                    </div>

                    {isEditingRelType && (
                      <form
                        onSubmit={handleUpdateRelType}
                        className="p-3.5 rounded-xl bg-surface-container-high/40 border border-starlight-white/10 space-y-3"
                      >
                        <div>
                          <label className="block text-[10px] text-on-surface-variant uppercase tracking-wider mb-1">
                            New Type *
                          </label>
                          <select
                            value={editRelType}
                            onChange={(e) => setEditRelType(e.target.value)}
                            className="w-full bg-surface-container-highest border border-starlight-white/10 rounded-lg px-2.5 py-1.5 text-xs text-starlight-white focus:outline-none focus:border-primary/50"
                          >
                            {COMMON_RELATIONSHIP_TYPES.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                            <option value="OTHER">Custom Type...</option>
                          </select>
                        </div>

                        {editRelType === 'OTHER' && (
                          <div>
                            <input
                              type="text"
                              placeholder="e.g. BETRAYED_BY"
                              value={customEditRelType}
                              onChange={(e) => setCustomEditRelType(e.target.value)}
                              className="w-full bg-surface-container-highest border border-starlight-white/10 rounded-lg px-2.5 py-1.5 text-xs text-starlight-white focus:outline-none focus:border-primary/50"
                            />
                          </div>
                        )}

                        <div>
                          <label className="block text-[10px] text-on-surface-variant uppercase tracking-wider mb-1">
                            Chapter Effective
                          </label>
                          <select
                            value={editRelChapterId}
                            onChange={(e) => setEditRelChapterId(e.target.value)}
                            className="w-full bg-surface-container-highest border border-starlight-white/10 rounded-lg px-2.5 py-1.5 text-xs text-starlight-white focus:outline-none focus:border-primary/50"
                          >
                            <option value="">Universal (No Chapter)</option>
                            {chapters.map((ch) => (
                              <option key={ch.id} value={ch.id}>
                                Chapter {ch.number}: {ch.title}
                              </option>
                            ))}
                          </select>
                        </div>

                        <button
                          type="submit"
                          disabled={updatingRel}
                          className="w-full py-1.5 px-3 rounded-lg bg-primary text-surface-container font-semibold text-xs hover:bg-primary/90 transition-colors disabled:opacity-50"
                        >
                          {updatingRel ? 'Updating...' : 'Append New Version'}
                        </button>
                      </form>
                    )}
                  </div>

                  {/* Version History Changelog */}
                  <div className="space-y-3">
                    <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
                      Evolution History ({selectedRelData.versions.length} versions)
                    </span>

                    <div className="space-y-2">
                      {selectedRelData.versions.map((ver, idx) => {
                        const isCurrent = ver.status === 'ACTIVE';
                        return (
                          <div
                            key={ver.id}
                            className={`p-3 rounded-lg border text-xs space-y-1 ${
                              isCurrent
                                ? 'bg-primary/5 border-primary/30'
                                : ver.status === 'CONTRADICTED'
                                ? 'bg-error/5 border-error/20'
                                : 'bg-surface-container-high/30 border-starlight-white/5'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono font-semibold text-starlight-white">
                                #{selectedRelData.versions.length - idx} {ver.relationship_type}
                              </span>
                              <span
                                className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${
                                  ver.status === 'ACTIVE'
                                    ? 'bg-primary/20 text-primary'
                                    : ver.status === 'CONTRADICTED'
                                    ? 'bg-error/20 text-error'
                                    : 'bg-white/10 text-on-surface-variant/60'
                                }`}
                              >
                                {ver.status}
                              </span>
                            </div>

                            <div className="text-[10px] text-on-surface-variant/60 flex items-center justify-between">
                              <span>
                                {ver.chapter_number !== null
                                  ? `Chapter ${ver.chapter_number}`
                                  : 'No Chapter'}
                              </span>
                              <span>Conf: {ver.confidence}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Danger Zone: Delete Relationship */}
                  <div className="pt-4 border-t border-starlight-white/10">
                    <button
                      onClick={handleDeleteRel}
                      className="w-full py-2 px-3 rounded-lg bg-error/10 hover:bg-error/20 text-error border border-error/30 text-xs font-semibold flex items-center justify-center gap-2 transition-colors"
                    >
                      <span className="material-symbols-outlined text-sm">delete</span>
                      Delete Relationship
                    </button>
                  </div>
                </>
              ) : (
                <p className="text-xs text-on-surface-variant/50">Click an edge to inspect.</p>
              )}
            </div>
          </aside>
        )}
      </main>

      {/* Add Relationship Modal */}
      {isAddRelOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-surface-container border border-starlight-white/10 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <h2 className="text-base font-bold text-starlight-white mb-4 flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">add_link</span>
              Establish Narrative Relationship
            </h2>

            <form onSubmit={handleCreateRelationship} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Source Entity *
                </label>
                <select
                  value={newRelSource}
                  aria-label="Source entity"
                  onChange={(e) => setNewRelSource(e.target.value)}
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                  required
                >
                  <option value="">Select source entity...</option>
                  {nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name} ({n.subtype})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Target Entity *
                </label>
                <select
                  value={newRelTarget}
                  aria-label="Target entity"
                  onChange={(e) => setNewRelTarget(e.target.value)}
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                  required
                >
                  <option value="">Select target entity...</option>
                  {nodes
                    .filter((n) => n.id !== newRelSource)
                    .map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.name} ({n.subtype})
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Relationship Type *
                </label>
                <select
                  value={newRelType}
                  onChange={(e) => setNewRelType(e.target.value)}
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                >
                  {COMMON_RELATIONSHIP_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                  <option value="OTHER">Custom Type...</option>
                </select>
              </div>

              {newRelType === 'OTHER' && (
                <div>
                  <input
                    type="text"
                    required
                    placeholder="Enter custom type, e.g. MENTOR_OF"
                    value={customNewRelType}
                    onChange={(e) => setCustomNewRelType(e.target.value)}
                    className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Effective Chapter
                </label>
                <select
                  value={newRelChapterId}
                  onChange={(e) => setNewRelChapterId(e.target.value)}
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                >
                  <option value="">Universal (Visible at all points)</option>
                  {chapters.map((ch) => (
                    <option key={ch.id} value={ch.id}>
                      Chapter {ch.number}: {ch.title}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-starlight-white/5">
                <button
                  type="button"
                  onClick={() => setIsAddRelOpen(false)}
                  className="px-4 py-2 rounded-lg text-sm text-on-surface-variant hover:text-starlight-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingRel || !newRelSource || !newRelTarget}
                  className="px-4 py-2 rounded-lg text-sm bg-primary text-surface-container font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {submittingRel ? 'Creating...' : 'Create Relationship'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
};
