import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

const SAMPLE_PAIRS = [
  ['Tomato', 'Bilaspur'], ['Onion', 'Raigarh'], ['Wheat', 'Raipur'],
  ['Paddy (Rice)', 'Durg'], ['Maize', 'Korba'], ['Chana (Gram)', 'Bilaspur'],
  ['Soybean', 'Raipur'], ['Groundnut', 'Durg'], ['Potato', 'Bilha'],
]

export default function PriceTicker() {
  const [items, setItems] = useState([])

  useEffect(() => {
    let mounted = true
    async function load() {
      try {
        const results = await Promise.all(
          SAMPLE_PAIRS.map(async ([crop, market]) => {
            const data = await api.getPrices(crop, market, 2)
            const rows = data?.rows || []
            const latest = rows[rows.length - 1]
            const prev = rows[rows.length - 2] || latest
            const change = latest && prev ? (((latest.modal_price - prev.modal_price) / prev.modal_price) * 100) : 0
            return { crop, market, price: latest?.modal_price, change }
          })
        )
        if (mounted) setItems(results.filter(r => r.price))
      } catch (e) {
        // silent -- ticker is decorative, don't block the page on it
      }
    }
    load()
    return () => { mounted = false }
  }, [])

  if (items.length === 0) return null

  const doubled = [...items, ...items]

  return (
    <div className="bg-ink text-paper overflow-hidden py-2.5 border-y border-marigold/20">
      <div className="flex whitespace-nowrap ticker-track w-max">
        {doubled.map((item, i) => (
          <div key={i} className="flex items-center gap-2 px-6 font-mono-data text-sm">
            <span className="text-paper/60">{item.crop} · {item.market}</span>
            <span className="font-semibold">₹{item.price}/qtl</span>
            <span className={item.change >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              {item.change >= 0 ? '▲' : '▼'} {Math.abs(item.change).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
