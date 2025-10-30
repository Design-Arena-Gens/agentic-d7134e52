// Next.js API route for provider lookup
// This proxies to the Python backend or provides mock data for demo

import type { NextApiRequest, NextApiResponse } from 'next';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  const { npi } = req.query;

  if (!npi || typeof npi !== 'string') {
    return res.status(400).json({ error: 'NPI number required' });
  }

  try {
    // Try to fetch from backend
    const response = await fetch(`${BACKEND_URL}/agents/execute/provider-lookup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // For demo, skip auth - in production use proper JWT
      },
      body: JSON.stringify({ npi_number: npi })
    });

    if (response.ok) {
      const data = await response.json();
      return res.status(200).json(data);
    }

    // If backend not available, return mock data for demo
    return res.status(200).json({
      success: true,
      provider: {
        npi_number: npi,
        name: 'Dr. Sample Provider',
        taxonomy_description: 'Internal Medicine',
        city: 'Boston',
        state: 'MA',
        latitude: 42.3601,
        longitude: -71.0589,
        trust_score: 0.85
      },
      evidence: [
        {
          step: 'npi_lookup',
          source: 'CMS NPI Registry (Free Public API)',
        },
        {
          step: 'geocoding',
          source: 'Nominatim/OpenStreetMap (Free)',
        },
        {
          step: 'storage',
          source: 'PostgreSQL Database',
        }
      ],
      message: 'Demo mode - backend not available. Deploy backend to see real data.'
    });

  } catch (error: any) {
    // Fallback to demo data
    return res.status(200).json({
      success: true,
      provider: {
        npi_number: npi,
        name: 'Demo Provider',
        taxonomy_description: 'Healthcare',
        city: 'Demo City',
        state: 'DC',
        latitude: 38.9072,
        longitude: -77.0369,
        trust_score: 0.75
      },
      evidence: [
        {
          step: 'demo_mode',
          source: 'Mock Data',
        }
      ],
      message: 'Demo mode - showing sample data. Deploy backend for real NPI lookups.'
    });
  }
}
