import './style.css'
import { resolveBrainWebSocketUrl } from '../networking/brainUrl'

type Portfolio = { fund?: Record<string, unknown>; demoData?: boolean }
const app = document.querySelector<HTMLElement>('#portfolio-app')!
const wsUrl = resolveBrainWebSocketUrl(import.meta.env.VITE_BRAIN_WS_URL)
let socket: WebSocket | null = null
let latestPortfolio: Portfolio | null = null
let reconnectTimer: number | null = null
let reconnectAttempt = 0
const money = (value: unknown) => typeof value === 'number' ? `$${value.toFixed(2)}` : '—'
const percent = (value: unknown) => typeof value === 'number' ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}%` : '—'
const isRealTxHash = (value: unknown): value is string => typeof value === 'string' && /^0x[a-fA-F0-9]{64}$/.test(value)
const TOKEN_LABELS: Record<string, string> = {
  '0x4a0e65a3eccec6dbe60ae065f2e7bb85fae35eea': 'SPCX',
  '0x6431d4a9e0566339bcf1bcd0f2723a531d64b788': 'LAMBO',
  '0xd0601ce157db5bdc3162bbac2a2c8af5320d9eec': 'NVDA',
  '0x3b4a0048a00787a644932cd648faa043410c163e': 'SIRIUS',
  '0x9aa0c0ca88e6ae43a3d229afc373c0b9f2b53521': 'PONIE',
  '0xc6132fdc41433b46cdf0374a7fb9a105752bb148': 'STONKFLY',
  '0xb6a906d2d95e862cf4fd43b9e30162aee19eed8d': 'ZFORGE',
  '0xc26e815246b767ba4ea238d625a9ba936efa7796': 'UNIFRONG',
}
const tokenLabel = (item: Record<string, unknown>) => {
  const symbol = String(item.tokenSymbol || item.symbol || '').trim()
  const address = String(item.tokenAddress || item.token_address || '').toLowerCase()
  return symbol && !/^0x[a-f0-9]{6,}$/i.test(symbol)
    ? symbol
    : TOKEN_LABELS[address] || (address ? `${address.slice(0, 6)}…${address.slice(-4)}` : 'TOKEN')
}
const nativeRaw = (value: unknown) => {
  if (typeof value !== 'string' || !/^\d+$/.test(value)) return '—'
  const whole = value.padStart(19, '0')
  const split = whole.length - 18
  return `${whole.slice(0, split)}.${whole.slice(split, split + 8)} ETH`
}
const mainnetExecutionCard = (item: Record<string, unknown>) => {
  const txHash = isRealTxHash(item.txHash) ? item.txHash : null
  if (!txHash) return ''
  const flyIds = Array.isArray(item.flyIds) ? item.flyIds.map(String).join(' · ') : '—'
  const side = String(item.side || '—').toUpperCase()
  const inputToken = String(item.inputToken || '')
  const input = inputToken === '0x0000000000000000000000000000000000000000' ? nativeRaw(item.inputAmount) : String(item.inputAmount || '—')
  const output = item.actualOutputAmount ?? item.expectedOutput ?? '—'
  const block = item.blockNumber ? `Block ${String(item.blockNumber)}` : 'Awaiting receipt'
  const gas = item.transactionFee ? nativeRaw(item.transactionFee) : '—'
  const status = String(item.status || 'PENDING')
  return `<article class="execution-card execution-${status.toLowerCase()}"><div class="execution-card-top"><strong>${flyIds}</strong><span>${status}</span></div><h3>${side} ${String(item.tokenSymbol || 'TOKEN')}</h3><div class="execution-route">${input} → ${String(output)} ${String(item.tokenSymbol || '')}</div><div class="execution-meta"><span>ROBINHOOD CHAIN</span><span>${block}</span><span>Gas ${gas}</span></div><a class="execution-link" href="https://robinhoodchain.blockscout.com/tx/${txHash}" target="_blank" rel="noopener noreferrer">VIEW ON BLOCKSCOUT ↗</a></article>`
}
const walletTransactionRow = (item: Record<string, unknown>) => {
  const txHash = isRealTxHash(item.txHash) ? item.txHash : ''
  if (!txHash) return ''
  const side = String(item.side || '').toUpperCase()
  const status = String(item.status || '—').toUpperCase()
  const input = String(item.actualInputAmount || item.inputAmount || '—')
  const output = String(item.actualOutputAmount || item.expectedOutput || '—')
  const token = String(item.tokenSymbol || item.tokenAddress || 'TOKEN')
  const block = item.blockNumber ? `BLOCK ${String(item.blockNumber)}` : 'PENDING'
  return `<div class="trade wallet-transaction-row"><b>${side}</b><span>${token}</span><span>${input} → ${output}</span><span>${status}</span><span>${block}</span><a href="https://robinhoodchain.blockscout.com/tx/${txHash}" target="_blank" rel="noopener noreferrer">VIEW TX ↗</a></div>`
}

function render(data: Portfolio | null, status = 'CONNECTING') {
  const fund = data?.fund || {}
  const legacyPositions = Array.isArray(fund.positions) ? fund.positions as Record<string, unknown>[] : []
  const trades = Array.isArray(fund.recentTrades) ? fund.recentTrades as Record<string, unknown>[] : []
  const chains = Array.isArray(fund.allocationByChain) ? fund.allocationByChain as Record<string, unknown>[] : []
  const security = (fund.security || {}) as Record<string, unknown>
  const wallet = (fund.wallet || {}) as Record<string, unknown>
  const allocation = (fund.allocation || {}) as Record<string, unknown>
  const autonomous = (fund.autonomous || {}) as Record<string, unknown>
  const flies = Array.isArray(autonomous.flies) ? autonomous.flies as Record<string, unknown>[] : []
  const actual = Array.isArray(autonomous.actualWalletPortfolio) ? autonomous.actualWalletPortfolio as Record<string, unknown>[] : []
  const mainnetExecutions = Array.isArray(autonomous.mainnetExecutions) ? autonomous.mainnetExecutions as Record<string, unknown>[] : []
  const walletTransactions = mainnetExecutions.filter((item) => {
    const status = String(item.status || '').toUpperCase()
    return isRealTxHash(item.txHash) && ['BROADCAST', 'PENDING', 'CONFIRMED', 'REVERTED'].includes(status)
  })
  const walletBuys = walletTransactions.filter((item) => String(item.side || '').toLowerCase() === 'buy')
  const walletSells = walletTransactions.filter((item) => String(item.side || '').toLowerCase() === 'sell')
  const native = (value: unknown) => typeof value === 'number' ? `${value.toFixed(6)} ETH` : '—'
  const observedTokenPositions = actual.filter((item) => {
    const address = String(item.tokenAddress || item.token_address || '')
    const amount = Number(item.observedAmount ?? item.amount ?? 0)
    return /^0x[a-fA-F0-9]{40}$/.test(address)
      && !/^0x0{40}$/i.test(address)
      && Number.isFinite(amount)
      && amount > 0
  })
  // The wallet observation is authoritative for what is held right now.
  // Ledger positions can lag after a broadcast, so prefer observed balances
  // whenever they are available and only use the ledger as a fallback.
  const positions = observedTokenPositions.length
    ? observedTokenPositions.map((item) => ({
      symbol: item.tokenSymbol,
      token_address: item.tokenAddress,
      chain_id: item.chainId,
      amount: item.observedAmount,
      value_usd: item.observedValueUsd,
      unrealized_pnl_usd: null,
    }))
    : legacyPositions
  const observedTokenValueUsd = observedTokenPositions.reduce((sum, item) => {
    const value = Number(item.observedValueUsd)
    return Number.isFinite(value) ? sum + value : sum
  }, 0)
  const walletAddress = String(wallet.address || fund.treasuryAddress || 'not configured')
  const walletExplorerLink = /^0x[a-fA-F0-9]{40}$/.test(walletAddress) ? `<a class="explorer-button" href="https://robinhoodchain.blockscout.com/address/${walletAddress}" target="_blank" rel="noopener noreferrer">WATCH WALLET ON BLOCKSCOUT ↗</a>` : ''
  const walletStatus = wallet.status === 'error' ? `RPC ERROR · ${String(wallet.error || 'unable to read balance')}` : wallet.configured ? 'RPC BALANCE LIVE' : 'WALLET NOT CONFIGURED'
  const walletChain = String(wallet.chainId || fund.chainId || '—')
  const displayedNav = typeof fund.navUsd === 'number' && fund.navUsd > 0
    ? money(fund.navUsd)
    : observedTokenValueUsd > 0
      ? money(observedTokenValueUsd)
    : typeof wallet.nativeBalance === 'number'
      ? `${wallet.nativeBalance.toFixed(6)} ${String(wallet.nativeSymbol || 'ETH')}`
      : money(fund.navUsd)
  const displayedReturn = typeof autonomous.portfolioReturnPct === 'number'
    ? percent(autonomous.portfolioReturnPct)
    : null
  const connectionNotice = data
    ? `${data.demoData ? 'DEMO DATA · NOT A LIVE PORTFOLIO' : 'ROBINHOOD WALLET · UNISWAP EXECUTION RUNTIME'} · ${walletStatus} · ${String(autonomous.executionAdapter || 'adapter pending')}`
    : `CONNECTING TO LIVE FUND · ${status}`
  app.innerHTML = `<header class="site-header"><a class="portfolio-brand site-brand" href="/" aria-label="FruitFly Capital home"><img src="/fruitfly-logo.png" alt="" /> <span>FRUITFLY CAPITAL</span></a><nav class="site-nav" aria-label="Primary navigation"><a href="/">Simulation</a><a href="/about/">About</a><a class="is-active" href="/portfolio/">Portfolio</a><a href="https://www.ponsfamily.com/launchpad/0x80f961956721E5670248fDD65da083A421E630D2" target="_blank" rel="noopener noreferrer">Buy</a><a href="https://robinhoodchain.blockscout.com/address/0x80f961956721e5670248fdd65da083a421e630d2" target="_blank" rel="noopener noreferrer" title="0x80f961956721e5670248fdd65da083a421e630d2">CA 0x80f9…30d2</a><a href="https://x.com/fruitflycap" target="_blank" rel="noreferrer">Community</a></nav><a class="social-link header-social" href="https://x.com/fruitflycap" target="_blank" rel="noreferrer" aria-label="FruitFly Capital on X"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.9 2H22l-6.77 7.74L23.2 22h-6.24l-4.89-6.39L6.48 22H3.36l7.24-8.28L2.8 2h6.4l4.42 5.84L18.9 2Zm-1.1 17.7h1.73L8.28 4.2H6.42L17.8 19.7Z" /></svg><span>@fruitflycap</span></a></header><div class="portfolio-title"><h1>FRUITFLY CAPITAL</h1><p>AUTONOMOUS BIOLOGICAL FUND</p></div>
    <section class="notice">${connectionNotice}</section>
    <section class="metrics">${[['WALLET TOTAL', native(wallet.nativeBalance)], ['AVAILABLE TO TRADE', native(wallet.availableToTrade)], ['GAS RESERVE', native(wallet.gasReserve)], ['PER FLY BUDGET', native(allocation.perFlyBudget)], ['TOTAL FUND NAV', displayedNav], ...(displayedReturn !== null ? [['FUND RETURN', displayedReturn]] : [])].map(([label, value]) => `<article><small>${label}</small><strong>${value}</strong></article>`).join('')}</section>
    <section class="panel wallet-summary"><div><small>ROBINHOOD WALLET</small><code>${walletAddress}</code></div><div><small>NATIVE BALANCE</small><strong>${native(wallet.nativeBalance)}</strong></div><div><small>AVAILABLE AFTER GAS RESERVE</small><strong>${native(wallet.availableToTrade)}</strong></div><div><small>CHAIN</small><strong>Robinhood · ${walletChain}</strong></div><div><small>RPC STATUS</small><strong class="wallet-status ${wallet.status === 'error' ? 'is-error' : ''}">${walletStatus}</strong></div>${walletExplorerLink}</section>
    <section class="panel"><h2>ACTUAL WALLET PORTFOLIO</h2>${actual.length ? actual.map(item => `<div class="trade"><b>${tokenLabel(item)}</b><span>${String(item.observedAmount ?? item.amount ?? '—')}</span></div>`).join('') : '<p class="muted">No token balances observed yet.</p>'}</section>
    <section class="grid"><article class="panel"><h2>PORTFOLIO ALLOCATION BY CHAIN</h2>${chains.length ? chains.map(item => `<div class="row"><span>CHAIN ${item.chainId}</span><b>${typeof item.weight === 'number' ? (item.weight * 100).toFixed(1) : '—'}%</b></div>`).join('') : '<p class="muted">No priced positions recorded.</p>'}</article>
      <article class="panel"><h2>WALLET &amp; EXECUTION</h2><div class="kv"><span>Wallet</span><code>${walletAddress}</code><span>Chain</span><b>Robinhood · ${walletChain}</b><span>Fly allocation</span><b>${typeof allocation.perFlyPercent === 'number' ? allocation.perFlyPercent.toFixed(2) : '—'}% · ${String(allocation.flyCount || '—')} flies</b><span>Execution</span><b>${String(fund.executionBoundary || '—').toUpperCase()}</b><span>Trade limit</span><b>${money(security.autonomousTradeLimitUsd)}</b></div></article></section>
    <section class="panel"><h2>POSITIONS</h2><div class="table"><div class="thead"><span>ASSET</span><span>CHAIN</span><span>AMOUNT</span><span>VALUE</span><span>P&L</span></div>${positions.length ? positions.map(item => `<div class="tr"><span>${tokenLabel(item)}</span><span>${String(item.chain_id || '—')}</span><span>${String(item.amount ?? '—')}</span><span>${money(item.value_usd)}</span><span>${money(item.unrealized_pnl_usd)}</span></div>`).join('') : '<p class="muted">No positions recorded yet.</p>'}</div></section>
    <section class="panel"><h2>RECENT FRUITFLY CAPITAL TRADES</h2>${trades.filter(item => isRealTxHash(item.tx_hash) && ['BROADCAST', 'PENDING', 'CONFIRMED', 'REVERTED'].includes(String(item.status || '').toUpperCase())).length ? trades.filter(item => isRealTxHash(item.tx_hash) && ['BROADCAST', 'PENDING', 'CONFIRMED', 'REVERTED'].includes(String(item.status || '').toUpperCase())).map(item => `<div class="trade"><b>${String(item.status || '—').toUpperCase()}</b><span>chain ${String(item.chain_id || '—')}</span><span>${money(item.usd_value)}</span><a href="https://robinhoodchain.blockscout.com/tx/${item.tx_hash}" target="_blank" rel="noopener noreferrer">VIEW TX ↗</a></div>`).join('') : '<p class="muted">No on-chain trades recorded yet.</p>'}</section>
    <section class="panel mainnet-executions"><h2>MAINNET EXECUTED · ROBINHOOD CHAIN</h2>${mainnetExecutions.length ? mainnetExecutions.map(mainnetExecutionCard).join('') : '<p class="muted">No real mainnet transaction hashes recorded.</p>'}</section>
    <section class="grid"><article class="panel"><h2>BUY TRANSACTIONS</h2>${walletBuys.length ? walletBuys.map(walletTransactionRow).join('') : '<p class="muted">No buy transactions recorded yet.</p>'}</article><article class="panel"><h2>SELL TRANSACTIONS</h2>${walletSells.length ? walletSells.map(walletTransactionRow).join('') : '<p class="muted">No sell transactions recorded yet.</p>'}</article></section>
    <footer><a href="./">FRUITFLY CAPITAL</a><button id="refresh">REFRESH</button><span>FruitFly Capital · MaleCNS · Flybody · The Graph</span></footer>`
  document.querySelector('#refresh')?.addEventListener('click', request)
}
function request() {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'portfolio_request' }))
    return
  }
  connect()
}
function connect() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return
  render(latestPortfolio, latestPortfolio ? 'RECONNECTING' : 'CONNECTING')
  const candidate = new WebSocket(wsUrl)
  socket = candidate
  candidate.addEventListener('open', () => {
    if (socket !== candidate) return
    reconnectAttempt = 0
    candidate.send(JSON.stringify({ type: 'portfolio_request' }))
  })
  candidate.addEventListener('message', event => {
    try {
      const message = JSON.parse(event.data)
      if (message.type !== 'portfolio_update') return
      latestPortfolio = message
      render(latestPortfolio, 'CONNECTED')
    } catch {
      render(latestPortfolio, 'INVALID RESPONSE')
    }
  })
  candidate.addEventListener('close', () => {
    if (socket !== candidate) return
    socket = null
    render(latestPortfolio, latestPortfolio ? 'RECONNECTING' : 'OFFLINE · RETRYING')
    if (reconnectTimer !== null) return
    const delay = Math.min(5000, 500 * 2 ** Math.min(reconnectAttempt, 4))
    reconnectAttempt += 1
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  })
}
render(null)
request()
window.setInterval(request, 5000)
