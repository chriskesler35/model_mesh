import { Suspense } from 'react'
import PersonaForm from './form'

export default function NewPersonaPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-[50vh]"><div className="text-gray-500">Loading...</div></div>}>
      <PersonaForm />
    </Suspense>
  )
}