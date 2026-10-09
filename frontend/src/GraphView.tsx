import { useEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { pageHref } from "./links";

interface GraphData {
  nodes: { id: string; title: string; tags: string[] }[];
  links: { source: string; target: string }[];
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name);

export function GraphView({ current }: { current: string }) {
  const [data, setData] = useState<GraphData | null>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/graph")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ nodes: [], links: [] }));
  }, []);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const update = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    update();
    const obs = new ResizeObserver(update);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div className="graph" ref={box}>
      {data && (
        <ForceGraph2D
          width={size.width}
          height={size.height}
          graphData={data}
          backgroundColor="rgba(0,0,0,0)"
          linkColor={() => css("--border")}
          nodeLabel="title"
          nodeRelSize={6}
          nodeColor={(n) => (n.id === current ? css("--accent") : css("--muted"))}
          onNodeClick={(n) => {
            window.location.hash = pageHref(String(n.id));
          }}
          nodeCanvasObjectMode={() => "after"}
          nodeCanvasObject={(n, ctx, scale) => {
            ctx.font = `${12 / scale}px sans-serif`;
            ctx.fillStyle = css("--text");
            ctx.textAlign = "center";
            ctx.fillText(String(n.title), n.x ?? 0, (n.y ?? 0) + 12 / scale + 4);
          }}
        />
      )}
    </div>
  );
}
