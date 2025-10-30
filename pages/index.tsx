import { useState } from 'react';
import Head from 'next/head';

export default function Home() {
  const [npiNumber, setNpiNumber] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const lookupProvider = async () => {
    if (!npiNumber) {
      setError('Please enter an NPI number');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    try {
      // For demo, call the backend API directly
      const response = await fetch(`/api/lookup?npi=${npiNumber}`);
      const data = await response.json();

      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to lookup provider');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <Head>
        <title>Healthcare AI Agentic System</title>
        <meta name="description" content="Production healthcare AI system with trust scoring" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-5xl font-bold text-gray-900 mb-4">
              Healthcare AI Agentic System
            </h1>
            <p className="text-xl text-gray-600">
              Provider verification with AI agents, trust scoring, and RAG
            </p>
            <div className="mt-4 flex justify-center gap-4 text-sm text-gray-500">
              <span>✓ Free OSS Stack</span>
              <span>✓ NPI Registry</span>
              <span>✓ OpenStreetMap Geocoding</span>
              <span>✓ NetworkX TrustRank</span>
            </div>
          </div>

          {/* Search Card */}
          <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
            <h2 className="text-2xl font-semibold text-gray-800 mb-6">
              Lookup Healthcare Provider
            </h2>

            <div className="flex gap-4 mb-6">
              <input
                type="text"
                placeholder="Enter NPI Number (e.g., 1003000126)"
                value={npiNumber}
                onChange={(e) => setNpiNumber(e.target.value)}
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                onKeyPress={(e) => e.key === 'Enter' && lookupProvider()}
              />
              <button
                onClick={lookupProvider}
                disabled={loading}
                className="px-8 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? 'Searching...' : 'Lookup'}
              </button>
            </div>

            {error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
                {error}
              </div>
            )}

            {result && (
              <div className="mt-6 space-y-4">
                <div className="p-6 bg-green-50 border border-green-200 rounded-lg">
                  <h3 className="text-xl font-semibold text-gray-800 mb-4">
                    Provider Found
                  </h3>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-gray-600">Name</p>
                      <p className="font-semibold">{result.provider?.name || 'N/A'}</p>
                    </div>

                    <div>
                      <p className="text-sm text-gray-600">NPI Number</p>
                      <p className="font-semibold">{result.provider?.npi_number || npiNumber}</p>
                    </div>

                    <div>
                      <p className="text-sm text-gray-600">Specialty</p>
                      <p className="font-semibold">{result.provider?.taxonomy_description || 'N/A'}</p>
                    </div>

                    <div>
                      <p className="text-sm text-gray-600">Location</p>
                      <p className="font-semibold">
                        {result.provider?.city}, {result.provider?.state}
                      </p>
                    </div>

                    {result.provider?.latitude && (
                      <div>
                        <p className="text-sm text-gray-600">Coordinates</p>
                        <p className="font-semibold">
                          {result.provider.latitude.toFixed(4)}, {result.provider.longitude.toFixed(4)}
                        </p>
                      </div>
                    )}

                    {result.provider?.trust_score && (
                      <div>
                        <p className="text-sm text-gray-600">Trust Score</p>
                        <p className="font-semibold text-green-600">
                          {(result.provider.trust_score * 100).toFixed(2)}%
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {result.evidence && result.evidence.length > 0 && (
                  <div className="p-6 bg-gray-50 border border-gray-200 rounded-lg">
                    <h3 className="text-lg font-semibold text-gray-800 mb-4">
                      Evidence Trail
                    </h3>

                    <div className="space-y-3">
                      {result.evidence.map((ev: any, idx: number) => (
                        <div key={idx} className="flex items-start gap-3">
                          <div className="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-sm">
                            {idx + 1}
                          </div>
                          <div className="flex-1">
                            <p className="font-medium text-gray-800">{ev.step}</p>
                            <p className="text-sm text-gray-600">{ev.source}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="text-3xl mb-3">🤖</div>
              <h3 className="text-lg font-semibold mb-2">AI Agents</h3>
              <p className="text-gray-600 text-sm">
                Meta-agent orchestrates NPI lookup, geocoding, and memory storage
              </p>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="text-3xl mb-3">🔗</div>
              <h3 className="text-lg font-semibold mb-2">Trust Graph</h3>
              <p className="text-gray-600 text-sm">
                NetworkX PageRank computes trust scores from provider relationships
              </p>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="text-3xl mb-3">🧠</div>
              <h3 className="text-lg font-semibold mb-2">RAG & LLM</h3>
              <p className="text-gray-600 text-sm">
                Sentence-transformers + TinyLlama for semantic search and reasoning
              </p>
            </div>
          </div>

          {/* Tech Stack */}
          <div className="mt-12 text-center text-sm text-gray-600">
            <p className="mb-2">
              <strong>Free OSS Stack:</strong> FastAPI • PostgreSQL • sentence-transformers • NetworkX • Next.js
            </p>
            <p>
              <strong>Free APIs:</strong> CMS NPI Registry • Nominatim/OpenStreetMap
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
