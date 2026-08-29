import { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries } from 'lightweight-charts'
import type { IChartApi } from 'lightweight-charts'
import axios from 'axios'
import { Calendar, TrendingUp, AlertTriangle, Play, Square, Settings } from 'lucide-react'

const API_BASE = 'http://127.0.0.1:8791'

export default function App() {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const [chart, setChart] = useState<IChartApi | null>(null)
  const [positions, setPositions] = useState<any>({})
  const [currentPrice, setCurrentPrice] = useState(20000.50) // Mock MNQ price
  
  useEffect(() => {
    if (!chartContainerRef.current) return
    
    const newChart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 500,
      layout: { background: { color: '#0a0a1a' }, textColor: '#d1d4dc' },
      grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
    })
    
    const candleSeries = newChart.addSeries(CandlestickSeries, {
      upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
      wickUpColor: '#26a69a', wickDownColor: '#ef5350'
    })
    
    // Mock Data for the chart
    const data = [
      { time: '2026-08-28', open: 20000, high: 20050, low: 19950, close: 20020 },
      { time: '2026-08-29', open: 20020, high: 20100, low: 20010, close: 20080 },
    ]
    candleSeries.setData(data)
    setChart(newChart)
    
    const resizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || entries[0].target !== chartContainerRef.current) return
      newChart.applyOptions({ width: chartContainerRef.current.clientWidth })
    })
    resizeObserver.observe(chartContainerRef.current)
    
    return () => { resizeObserver.disconnect(); newChart.remove() }
  }, [])

  const fetchPositions = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/positions`)
      setPositions(res.data.positions)
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    fetchPositions()
    const int = setInterval(fetchPositions, 2000)
    return () => clearInterval(int)
  }, [])

  const buyMarket = async () => {
    await axios.post(`${API_BASE}/api/order/submit`, {
      symbol: 'MNQ', side: 'LONG', qty: 1, price: currentPrice, stop_loss: currentPrice - 20
    })
    fetchPositions()
  }

  const closePos = async (symbol: string) => {
    await axios.post(`${API_BASE}/api/positions/${symbol}/close?price=${currentPrice}`)
    fetchPositions()
  }

  const updateStop = async (symbol: string, newStop: number) => {
    await axios.post(`${API_BASE}/api/positions/${symbol}/stop`, { symbol, new_stop: newStop })
    fetchPositions()
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 p-4 font-sans">
      <div className="flex gap-4 mb-4">
        <h1 className="text-2xl font-bold text-teal-400 flex items-center gap-2">
          <TrendingUp /> Tradayri Terminal
        </h1>
        <div className="ml-auto flex items-center gap-4 bg-slate-800 p-2 rounded">
          <span className="text-sm">MNQ Price: <b className="text-white">{currentPrice.toFixed(2)}</b></span>
          <button onClick={buyMarket} className="bg-teal-600 hover:bg-teal-500 text-white px-4 py-1 rounded">Buy MKT</button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Chart Area */}
        <div className="col-span-9 bg-slate-800 rounded-lg p-2 h-[520px]">
          <div ref={chartContainerRef} className="w-full h-full" />
        </div>
        
        {/* Sidebar - Calendar & Risk */}
        <div className="col-span-3 flex flex-col gap-4">
          <div className="bg-slate-800 p-4 rounded-lg flex-1">
            <h2 className="text-lg font-bold mb-2 flex items-center gap-2"><AlertTriangle size={18}/> Risk Engine</h2>
            <div className="text-sm text-slate-400 space-y-2">
              <p>Max Daily Loss: <span className="text-white">$500.00</span></p>
              <p>Current PnL: <span className="text-emerald-400">$0.00</span></p>
              <p>Rule Profile: <span className="text-white">Lucid 25k Pro</span></p>
            </div>
          </div>
          
          <div className="bg-slate-800 p-4 rounded-lg flex-1">
            <h2 className="text-lg font-bold mb-2 flex items-center gap-2"><Calendar size={18}/> Economic Calendar</h2>
            <ul className="text-sm space-y-3">
              <li className="flex justify-between border-b border-slate-700 pb-1">
                <span>10:00 AM (EST)</span>
                <span className="text-red-400 font-bold">ISM Services PMI</span>
              </li>
              <li className="flex justify-between border-b border-slate-700 pb-1">
                <span>14:00 PM (EST)</span>
                <span className="text-orange-400">FOMC Minutes</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      {/* Positions Area */}
      <div className="mt-4 bg-slate-800 p-4 rounded-lg">
        <h2 className="text-lg font-bold mb-2 border-b border-slate-700 pb-2">Active Positions</h2>
        {Object.keys(positions).length === 0 ? (
          <p className="text-slate-500 text-sm italic">No open positions.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-slate-400">
                <th className="pb-2">Symbol</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Qty</th>
                <th className="pb-2">Entry</th>
                <th className="pb-2">Stop Loss</th>
                <th className="pb-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {Object.values(positions).map((pos: any) => (
                <tr key={pos.symbol} className="border-t border-slate-700">
                  <td className="py-2">{pos.symbol}</td>
                  <td className={`py-2 ${pos.side === 'LONG' ? 'text-teal-400' : 'text-red-400'}`}>{pos.side}</td>
                  <td className="py-2">{pos.qty}</td>
                  <td className="py-2">{pos.entry_price.toFixed(2)}</td>
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      {pos.stop_loss?.toFixed(2) || 'None'}
                      <button onClick={() => updateStop(pos.symbol, pos.stop_loss + 5)} className="text-xs bg-slate-700 px-2 py-1 rounded hover:bg-slate-600">Trail +5</button>
                    </div>
                  </td>
                  <td className="py-2">
                    <button onClick={() => closePos(pos.symbol)} className="text-red-400 hover:text-red-300">Close</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
