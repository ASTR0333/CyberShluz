import { useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { X } from 'lucide-react';
import { getAuth } from '../api/mocks';

function buildWsUrl(standId: string, token: string): string {
  const base = import.meta.env.VITE_API_URL || '/api/v1';

  const httpUrl = new URL(base, window.location.origin);
  const wsProto = httpUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  const path = `${httpUrl.pathname.replace(/\/$/, '')}/stand/${standId}/terminal`;
  return `${wsProto}//${httpUrl.host}${path}?token=${encodeURIComponent(token)}`;
}

export function StandTerminal({ standId, onClose }: { standId: string; onClose: () => void }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = getAuth()?.access_token;
    if (!containerRef.current || !token) return;

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 13,
      theme: { background: '#000000', foreground: '#d4d4d4' },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();

    const ws = new WebSocket(buildWsUrl(standId, token));

    const sendResize = () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    };

    ws.onopen = () => {
      term.writeln('\x1b[36mПодключение к стенду…\x1b[0m');
      sendResize();
    };
    ws.onmessage = (ev) => term.write(ev.data);
    ws.onclose = () => term.writeln('\r\n\x1b[33m[сессия закрыта]\x1b[0m');
    ws.onerror = () => term.writeln('\r\n\x1b[31m[ошибка соединения]\x1b[0m');

    const dataDisp = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data);
    });

    const onWinResize = () => {
      fit.fit();
      sendResize();
    };
    window.addEventListener('resize', onWinResize);

    return () => {
      window.removeEventListener('resize', onWinResize);
      dataDisp.dispose();
      ws.close();
      term.dispose();
    };
  }, [standId]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="w-full max-w-5xl bg-[#1E1E1E] rounded-brand overflow-hidden shadow-2xl border border-gray-700 flex flex-col">
        <div className="bg-[#2D2D2D] px-4 py-2 border-b border-gray-900 flex items-center justify-between flex-shrink-0">
          <span className="text-xs font-mono text-gray-300 uppercase tracking-widest">
            Веб-терминал — стенд #{standId}
          </span>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
            title="Закрыть"
          >
            <X size={16} />
          </button>
        </div>
        <div ref={containerRef} className="p-3 bg-black h-[60vh]" />
      </div>
    </div>
  );
}
