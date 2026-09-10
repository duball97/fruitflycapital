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
  const allocation = (fund.allocation || {}) as Record<string, unknown>
  const autonomous = (fund.autonomous || {}) as Record<string, unknown>
  const flies = Array.isArray(autonomous.flies) ? autonomous.flies as Record<string, unknown>[] : []
  const target = Array.isArray(autonomous.biologicalTargetPortfolio) ? autonomous.biologicalTargetPortfolio as Record<string, unknown>[] : []
  const actual = Array.isArray(autonomous.actualWalletPortfolio) ? autonomous.actualWalletPortfolio as Record<string, unknown>[] : []
  const events = Array.isArray(autonomous.events) ? autonomous.events as Record<string, unknown>[] : []
  const pending = Array.isArray(autonomous.pendingRebalance) ? autonomous.pendingRebalance as Record<string, unknown>[] : []
  const native = (value: unknown) => typeof value === 'number' ? `${value.toFixed(6)} ETH` : '—'
  const walletAddress = String(wallet.address || fund.treasuryAddress || 'not configured')
  const walletStatus = wallet.status === 'error' ? `RPC ERROR · ${String(wallet.error || 'unable to read balance')}` : wallet.configured ? 'RPC BALANCE LIVE' : 'WALLET NOT CONFIGURED'
  const walletChain = String(wallet.chainId || fund.chainId || '—')
  app.innerHTML = `<header><div><a class="portfolio-brand" href="./"><img src="/fruitfly-logo.png" alt="FruitFly Capital logo" /> <span>FRUITFLY CAPITAL</span></a><h1>FRUITFLY CAPITAL</h1><p>AUTONOMOUS BIOLOGICAL FUND</p></div><div class="portfolio-header-actions"><a class="social-link" href="https://x.com/fruitflycap" target="_blank" rel="noreferrer" aria-label="FruitFly Capital on X"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.9 2H22l-6.77 7.74L23.2 22h-6.24l-4.89-6.39L6.48 22H3.36l7.24-8.28L2.8 2h6.4l4.42 5.84L18.9 2Zm-1.1 17.7h1.73L8.28 4.2H6.42L17.8 19.7Z" /></svg><span>@fruitflycap</span></a><div class="badges"><span>${String(fund.mode || 'dry-run').toUpperCase()}</span><span>${status}</span></div></div></header>
    <section class="notice">${data?.demoData ? 'DEMO DATA · NOT A LIVE PORTFOLIO' : 'ROBINHOOD WALLET · UNISWAP EXECUTION RUNTIME'} · ${walletStatus} · ${String(autonomous.executionAdapter || 'adapter pending')} · retained vault contract inactive</section>
    <section class="metrics">${[['WALLET TOTAL', native(wallet.nativeBalance)], ['AVAILABLE TO TRADE', native(wallet.availableToTrade)], ['GAS RESERVE', native(wallet.gasReserve)], ['PER FLY BUDGET', native(allocation.perFlyBudget)], ['TOTAL FUND NAV', money(fund.navUsd)], ['FUND RETURN', percent(fund.returnPct)]].map(([label, value]) => `<article><small>${label}</small><strong>${value}</strong></article>`).join('')}</section>
    <section class="panel wallet-summary"><div><small>ROBINHOOD WALLET</small><code>${walletAddress}</code></div><div><small>NATIVE BALANCE</small><strong>${native(wallet.nativeBalance)}</strong></div><div><small>AVAILABLE AFTER GAS RESERVE</small><strong>${native(wallet.availableToTrade)}</strong></div><div><small>CHAIN</small><strong>Robinhood · ${walletChain}</strong></div><div><small>RPC STATUS</small><strong class="wallet-status ${wallet.status === 'error' ? 'is-error' : ''}">${walletStatus}</strong></div><p>Balance is read from the server wallet configured by <code>FUND_RPC_URL</code>. Simulation fills automatically; mainnet stops at unsigned transaction preparation for external authorization.</p></section>
    <section class="panel"><h2>16-BRAIN ALLOCATION STATE</h2><div class="table"><div class="thead"><span>FLY</span><span>STATE</span><span>TOKEN</span><span>VALUE</span><span>REALIZED</span><span>UNREALIZED</span></div>${flies.map(item => `<div class="tr"><span>${String(item.flyId || '—')}</span><span>${String(item.state || '—')}</span><span>${String(item.tokenSymbol || item.tokenAddress || 'EXPLORING')}</span><span>${money(item.currentValueUsd)}</span><span>${money(item.realizedPnlUsd)}</span><span>${money(item.unrealizedPnlUsd)}</span></div>`).join('') || '<p class="muted">No fly state received yet.</p>'}</div></section>
    <section class="grid"><article class="panel"><h2>BIOLOGICAL TARGET PORTFOLIO</h2>${target.length ? target.map(item => `<div class="row"><span>${String(item.tokenAddress || '—')}</span><b>${typeof item.allocationPercent === 'number' ? item.allocationPercent.toFixed(2) : '0.00'}%</b></div>`).join('') : '<p class="muted">No fly is holding a token.</p>'}</article><article class="panel"><h2>ACTUAL WALLET PORTFOLIO</h2>${actual.length ? actual.map(item => `<div class="trade"><b>${String(item.tokenSymbol || item.tokenAddress || '—')}</b><span>planned ${String(item.intendedAmount ?? '—')}</span><span>observed ${String(item.observedAmount ?? '—')}</span><span>${String(item.reconciliation || item.observationError || 'pending')}</span></div>`).join('') : '<p class="muted">No token balances observed yet.</p>'}</article></section>
    <section class="grid"><article class="panel"><h2>PORTFOLIO ALLOCATION BY CHAIN</h2>${chains.length ? chains.map(item => `<div class="row"><span>CHAIN ${item.chainId}</span><b>${typeof item.weight === 'number' ? (item.weight * 100).toFixed(1) : '—'}%</b></div>`).join('') : '<p class="muted">No priced positions recorded.</p>'}</article>
      <article class="panel"><h2>WALLET &amp; EXECUTION</h2><div class="kv"><span>Wallet</span><code>${walletAddress}</code><span>Chain</span><b>Robinhood · ${walletChain}</b><span>Fly allocation</span><b>${typeof allocation.perFlyPercent === 'number' ? allocation.perFlyPercent.toFixed(2) : '—'}% · ${String(allocation.flyCount || '—')} flies</b><span>Legacy vault</span><code>${String(fund.contractAddress || 'not configured · inactive')}</code><span>Execution</span><b>${String(fund.executionBoundary || '—').toUpperCase()}</b><span>Trade limit</span><b>${money(security.autonomousTradeLimitUsd)}</b></div></article></section>
    <section class="panel"><h2>POSITIONS</h2><div class="table"><div class="thead"><span>ASSET</span><span>CHAIN</span><span>AMOUNT</span><span>VALUE</span><span>P&L</span></div>${positions.length ? positions.map(item => `<div class="tr"><span>${String(item.symbol || item.token_address || '—')}</span><span>${String(item.chain_id || '—')}</span><span>${String(item.amount ?? '—')}</span><span>${money(item.value_usd)}</span><span>${money(item.unrealized_pnl_usd)}</span></div>`).join('') : '<p class="muted">No positions recorded yet.</p>'}</div></section>
    <section class="panel"><h2>RECENT FRUITFLY CAPITAL TRADES</h2>${trades.length ? trades.map(item => `<div class="trade"><b>${String(item.status || '—').toUpperCase()}</b><span>chain ${String(item.chain_id || '—')}</span><span>${money(item.usd_value)}</span><span>round ${String(item.round_id || '—')}</span></div>`).join('') : '<p class="muted">No trades recorded. Dry-run intents remain proposals until explicitly executed.</p>'}</section>
    <section class="grid"><article class="panel"><h2>BUY / HOLD / SELL EVENTS</h2>${events.length ? events.slice().reverse().slice(0, 20).map(item => `<div class="trade"><b>${String(item.type || '—')}</b><span>${String(item.flyId || (Array.isArray(item.flyIds) ? item.flyIds.join(', ') : '—'))}</span><span>${String(item.status || '—')}</span><span>${String(item.tokenAddress || item.reason || '—')}</span><span>price ${String(item.executionPrice ?? '—')}</span><span>gas ${String(item.gas ?? item.estimatedGas ?? '—')}</span><span>slip ${String(item.slippage ?? '—')}%</span></div>`).join('') : '<p class="muted">No autonomous events yet.</p>'}</article><article class="panel"><h2>PENDING REBALANCE</h2>${pending.length ? pending.slice().reverse().map(item => `<div class="trade"><b>${String(item.status || '—').toUpperCase()}</b><span>${String(item.side || '—')}</span><span>${String(item.tokenAddress || '—')}</span><span>${String(item.reason || '—')}</span></div>`).join('') : '<p class="muted">No pending rebalance.</p>'}</article></section>
    <footer><a href="./">FRUITFLY CAPITAL</a><button id="refresh">REFRESH</button><span>FruitFly Capital · MaleCNS · Flybody · The Graph</span></footer>`
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
