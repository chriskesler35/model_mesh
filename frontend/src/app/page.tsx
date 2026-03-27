import Link from 'next/link'
import { api } from '@/lib/api'

export default async function Home() {
  let personas = []
  let models = []
  
  try {
    const [personasRes, modelsRes] = await Promise.all([
      api.getPersonas(),
      api.getModels(),
    ])
    personas = personasRes.data
    models = modelsRes.data
  } catch (e) {
    // Handle error gracefully
    console.error('Failed to fetch data:', e)
  }

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-bold mb-8">ModelMesh Dashboard</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold">Personas</h2>
          <p className="text-3xl">{personas.length}</p>
          <Link href="/personas" className="text-blue-500 hover:underline">
            View all →
          </Link>
        </div>
        
        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold">Models</h2>
          <p className="text-3xl">{models.length}</p>
          <Link href="/models" className="text-blue-500 hover:underline">
            View all →
          </Link>
        </div>
        
        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold">Conversations</h2>
          <p className="text-3xl">—</p>
          <Link href="/conversations" className="text-blue-500 hover:underline">
            View all →
          </Link>
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold mb-4">Quick Stats</h2>
          <Link href="/stats" className="text-blue-500 hover:underline">
            View statistics →
          </Link>
        </div>
        
        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold mb-4">Recent Activity</h2>
          <p className="text-gray-500">No recent activity</p>
        </div>
      </div>
    </main>
  )
}