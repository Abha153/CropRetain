import React from 'react'
import { Routes, Route } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'

import Landing from './pages/Landing'
import Auth from './pages/Auth'
import FarmerDashboard from './pages/FarmerDashboard'
import BuyerDashboard from './pages/BuyerDashboard'
import MarketIntelligence from './pages/MarketIntelligence'
import AIAdvisor from './pages/AIAdvisor'
import PriceForecast from './pages/PriceForecast'
import Marketplace from './pages/Marketplace'
import FarmPool from './pages/FarmPool'
import ProfitCalculator from './pages/ProfitCalculator'
import GroupSelling from './pages/GroupSelling'
import Notifications from './pages/Notifications'
import Profile from './pages/Profile'
import AdminDashboard from './pages/AdminDashboard'
import AskAssistant from './pages/AskAssistant'
// Phase 1-13 new pages
import Lots from './pages/Lots'
import BuyerDemands from './pages/BuyerDemands'
import BuyerVerification from './pages/BuyerVerification'
import Transactions from './pages/Transactions'
import TransactionDetail from './pages/TransactionDetail'
// Phase 6-18 new pages
import Storage from './pages/Storage'
import Transport from './pages/Transport'
import TransporterDashboard from './pages/TransporterDashboard'
import ArrivalIntelligence from './pages/ArrivalIntelligence'
import BestOption from './pages/BestOption'

function Protected({ children, role }) {
  return (
    <ProtectedRoute requiredRole={role}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Auth mode="login" />} />
      <Route path="/register" element={<Auth mode="register" />} />

      <Route path="/farmer/dashboard" element={<Protected role="farmer"><FarmerDashboard /></Protected>} />
      <Route path="/buyer/dashboard" element={<Protected role="buyer"><BuyerDashboard /></Protected>} />

      <Route path="/market-intelligence" element={<Protected><MarketIntelligence /></Protected>} />
      <Route path="/advisor" element={<Protected role="farmer"><AIAdvisor /></Protected>} />
      <Route path="/forecast" element={<Protected><PriceForecast /></Protected>} />
      <Route path="/marketplace" element={<Protected><Marketplace /></Protected>} />
      <Route path="/farmpool" element={<Protected role="farmer"><FarmPool /></Protected>} />
      <Route path="/profit-calculator" element={<Protected role="farmer"><ProfitCalculator /></Protected>} />
      <Route path="/group-selling" element={<Protected role="farmer"><GroupSelling /></Protected>} />
      <Route path="/notifications" element={<Protected role="farmer"><Notifications /></Protected>} />
      <Route path="/profile" element={<Protected><Profile /></Protected>} />
      <Route path="/admin" element={<div className="min-h-screen bg-paper p-6 md:p-10"><AdminDashboard /></div>} />
      <Route path="/ask" element={<Protected><AskAssistant /></Protected>} />

      {/* Phase 1-13 new routes */}
      <Route path="/lots" element={<Protected><Lots /></Protected>} />
      <Route path="/buyer-demands" element={<Protected><BuyerDemands /></Protected>} />
      <Route path="/buyer-verification" element={<Protected role="buyer"><BuyerVerification /></Protected>} />
      <Route path="/transactions" element={<Protected><Transactions /></Protected>} />
      <Route path="/transactions/:id" element={<Protected><TransactionDetail /></Protected>} />
      {/* Admin verification route */}
      <Route path="/admin/verification" element={<div className="min-h-screen bg-paper p-6 md:p-10"><BuyerVerification /></div>} />
      {/* Phase 6-18 new routes */}
      <Route path="/storage" element={<Protected><Storage /></Protected>} />
      <Route path="/transport" element={<Protected role="farmer"><Transport /></Protected>} />
      <Route path="/transporter/dashboard" element={<Protected role="transporter"><TransporterDashboard /></Protected>} />
      <Route path="/arrivals" element={<Protected><ArrivalIntelligence /></Protected>} />
      <Route path="/best-option" element={<Protected><BestOption /></Protected>} />

      <Route path="*" element={<Landing />} />
    </Routes>
  )
}
