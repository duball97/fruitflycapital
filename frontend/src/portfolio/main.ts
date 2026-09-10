import './style.css'

type Portfolio = { fund?: Record<string, unknown>; demoData?: boolean }
const app = document.querySelector<HTMLElement>('#portfolio-app')!
const wsUrl = import.meta.env.VITE_BRAIN_WS_URL || 'ws://127.0.0.1:8765'
const money = (value: unknown) => typeof value === 'number' ? `$${value.toFixed(2)}` : '—'
const percent = (value: unknown) => typeof value === 'number' ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}%` : '—'

function render(data: Portfolio | null, status = 'CONNECTING') {
  const fund = data?.fund || {}
  const positions = Array.isArray(fund.positions) ? fund.positions as Record<string, unknown>[] : []
  const trades = Array.isArray(fund.recentTrades) ? fund.recentTrades as Record<string, unknown>[] : []
  const chains = Array.isArray(fund.allocationByChain) ? fund.allocationByChain as Record<string, unknown>[] : []
  const security = (fund.security || {}) as Record<string, unknown>
  const wallet = (fund.wallet || {}) as Record<string, unknown>
  const native = (value: unknown) => typeof value === 'number' ? `${value.toFixed(6)} ETH` : '—'
  app.innerHTML = `<header><div><a href="./">← NEUROSWARM</a><h1>FRUIT FLY CAPITAL</h1><p>AUTONOMOUS BIOLOGICAL FUND</p></div><div class="badges"><span>${String(fund.mode || 'dry-run').toUpperCase()}</span><span>${status}</span></div></header>
    <section class="notice">${data?.demoData ? 'DEMO DATA · NOT A LIVE PORTFOLIO' : 'SERVER WALLET · DIRECT UNISWAP ROUTING'} · ${wallet.configured ? 'RPC balance live' : 'wallet not configured'} · contracts retained but inactive</section>
    <section class="metrics">${[['WALLET TOTAL', native(wallet.nativeBalance)], ['AVAILABLE TO TRADE', native(wallet.availableToTrade)], ['GAS RESERVE', native(wallet.gasReserve)], ['TOTAL FUND NAV', money(fund.navUsd)], ['FUND RETURN', percent(fund.returnPct)], ['SHARES', typeof fund.sharesOutstanding === 'number' ? fund.sharesOutstanding.toFixed(4) : '—']].map(([label, value]) => `<article><small>${label}</small><strong>${value}</strong></article>`).join('')}</section>
    <section class="grid"><article class="panel"><h2>PORTFOLIO ALLOCATION BY CHAIN</h2>${chains.length ? chains.map(item => `<div class="row"><span>CHAIN ${item.chainId}</span><b>${typeof item.weight === 'number' ? (item.weight * 100).toFixed(1) : '—'}%</b></div>`).join('') : '<p class="muted">No priced positions recorded.</p>'}</article>
      <article class="panel"><h2>FUND INFRASTRUCTURE</h2><div class="kv"><span>Wallet</span><code>${String(wallet.address || fund.treasuryAddress || 'not configured')}</code><span>Chain</span><b>${String(fund.chainId || '—')}</b><span>Contract</span><code>${String(fund.contractAddress || 'retained · inactive')}</code><span>Execution</span><b>${String(fund.executionBoundary || '—').toUpperCase()}</b><span>Trade limit</span><b>${money(security.autonomousTradeLimitUsd)}</b></div></article></section>
    <section class="panel"><h2>POSITIONS</h2><div class="table"><div class="thead"><span>ASSET</span><span>CHAIN</span><span>AMOUNT</span><span>VALUE</span><span>P&L</span></div>${positions.length ? positions.map(item => `<div class="tr"><span>${String(item.symbol || item.token_address || '—')}</span><span>${String(item.chain_id || '—')}</span><span>${String(item.amount ?? '—')}</span><span>${money(item.value_usd)}</span><span>${money(item.unrealized_pnl_usd)}</span></div>`).join('') : '<p class="muted">No positions recorded yet.</p>'}</div></section>
    <section class="panel"><h2>RECENT NEUROSWARM TRADES</h2>${trades.length ? trades.map(item => `<div class="trade"><b>${String(item.status || '—').toUpperCase()}</b><span>chain ${String(item.chain_id || '—')}</span><span>${money(item.usd_value)}</span><span>round ${String(item.round_id || '—')}</span></div>`).join('') : '<p class="muted">No trades recorded. Dry-run intents remain proposals until explicitly executed.</p>'}</section>
    <footer><a href="./">NEUROSWARM</a><button id="refresh">REFRESH</button><span>Fruit Fly Capital · MaleCNS · Flybody · The Graph</span></footer>`
  document.querySelector('#refresh')?.addEventListener('click', request)
}
function request() {
  render(null, 'CONNECTING')
  const socket = new WebSocket(wsUrl)
  socket.addEventListener('open', () => socket.send(JSON.stringify({ type: 'portfolio_request' })))
  socket.addEventListener('message', event => { try { const message = JSON.parse(event.data); if (message.type === 'portfolio_update') render(message, 'CONNECTED') } catch { render(null, 'ERROR') } })
  socket.addEventListener('error', () => render(null, 'OFFLINE'))
}
render(null)
request()
