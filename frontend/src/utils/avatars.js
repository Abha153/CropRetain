// Centralized avatar mapping for CropRetain demo users.
//
// IMPORTANT: this is completely separate from CropRetain product branding
// (favicon/logo live in /public and are referenced directly in index.html
// and Layout.jsx). This file only maps individual seeded farmer/buyer
// records to their individual portrait assets under /avatars/.
//
// Portraits were extracted from a reference collage into single-person,
// text-free, logo-free images at frontend/public/avatars/{farmers,buyers}/.
// There are 5 distinct portraits per role; seeded demo accounts are mapped
// onto them below (reused across accounts where the seed list is longer
// than the portrait set -- there is no unique portrait per person beyond
// that pool).

const FARMER_AVATAR_BY_NAME = {
  'Ramesh Kumar': '/avatars/farmers/farmer-01.png',
  'Sunita Verma': '/avatars/farmers/farmer-02.png',
  'Manoj Sahu': '/avatars/farmers/farmer-03.png',
  'Preeti': '/avatars/farmers/farmer-04.png',
  'Dilip Nirmalkar': '/avatars/farmers/farmer-05.png',
  'Kavita Patel': '/avatars/farmers/farmer-02.png',
  'Ganesh Yadav': '/avatars/farmers/farmer-01.png',
  'Anita Dewangan': '/avatars/farmers/farmer-04.png',
  'Prakash Baghel': '/avatars/farmers/farmer-03.png',
  'Meena Sinha': '/avatars/farmers/farmer-02.png',
}

const BUYER_AVATAR_BY_COMPANY = {
  'FreshFoods Processing Pvt. Ltd.': '/avatars/buyers/buyer-01.png',
  'GreenBasket Retail': '/avatars/buyers/buyer-02.png',
  'AgriExport India': '/avatars/buyers/buyer-03.png',
  'Chhattisgarh Wholesale Traders': '/avatars/buyers/buyer-04.png',
  'Kisan Limited': '/avatars/buyers/buyer-05.png',
  'KisanKart': '/avatars/buyers/buyer-01.png',
  'FarmLink Agro': '/avatars/buyers/buyer-02.png',
  'GreenRoute Foods': '/avatars/buyers/buyer-03.png',
  'Bharat Harvest': '/avatars/buyers/buyer-04.png',
  'CropBridge': '/avatars/buyers/buyer-05.png',
}

/**
 * Resolve an avatar image path for a seeded farmer or buyer.
 * Returns null when no portrait is mapped -- callers should fall back to
 * an initials avatar in that case (never the CropRetain logo).
 */
export function getAvatarUrl(role, identity) {
  if (!identity) return null
  if (role === 'buyer') return BUYER_AVATAR_BY_COMPANY[identity] || null
  return FARMER_AVATAR_BY_NAME[identity] || null
}
