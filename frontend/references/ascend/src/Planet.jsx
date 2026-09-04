import { useEffect, useRef } from 'react'
import { initPlanet } from './scene/planet.js'

// Fixed full-viewport WebGL canvas sitting behind the hero. pointer-events are
// off (see index.css) so it never intercepts scroll or clicks.
export default function Planet() {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (!canvasRef.current) return
    const cleanup = initPlanet(canvasRef.current)
    return cleanup
  }, [])

  return <canvas ref={canvasRef} className="planet-canvas" aria-hidden="true" />
}
