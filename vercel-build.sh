#!/bin/bash

# ==============================================
# NexaWorks HRMS - Vercel Build Script
# ==============================================

echo "🚀 Starting NexaWorks HRMS build for Vercel..."

# Build Frontend (React + Vite)
echo "📦 Building frontend..."
cd frontend
npm install
npm run build
cd ..

# ==============================================
# IMPORTANT: better-sqlite3 will NOT work on Vercel
# The backend API endpoints will fail
# Your NexaBot AI assistant needs a real database
# ==============================================

# Create mock backend for Vercel (so build doesn't fail)
echo "⚠️  Creating mock backend for Vercel compatibility..."
mkdir -p backend/node_modules
mkdir -p backend/data

# Create a dummy database.js that works in read-only mode
cat > backend/src/db/database-vercel.js << 'EOF'
// Vercel-compatible mock database
// Your actual better-sqlite3 won't work here
console.warn("⚠️  Running on Vercel - Database operations will be limited");

// Mock database for Vercel deployment
export const db = {
  prepare: () => ({
    all: () => [],
    get: () => null,
    run: () => ({ changes: 0, lastInsertRowid: 0 })
  }),
  exec: () => {},
  pragma: () => {}
};

export default { db };
EOF

echo "✅ Build complete for Vercel deployment"
echo ""
echo "⚠️  IMPORTANT NOTES:"
echo "   - better-sqlite3 does NOT work on Vercel serverless"
echo "   - Your NexaBot AI assistant will NOT function"
echo "   - Employee CRUD operations will FAIL"
echo "   - Only static frontend will work properly"
echo ""
echo "💡 RECOMMENDATION:"
echo "   Deploy backend separately on Railway/Fly.io"
echo "   Set VITE_API_URL environment variable to your backend URL"
