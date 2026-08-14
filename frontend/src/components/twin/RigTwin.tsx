import { Canvas, useFrame } from '@react-three/fiber'
import { AdaptiveDpr, Line, OrbitControls } from '@react-three/drei'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { useStreamStore } from '../../store/streamStore'
import type { TwinStateMsg } from '../../lib/types'

const N_JOINTS = 48
const RADIAL_X = 50

function visualRpm(rpm: number): number {
  // Stroboscope-safe: render sub-multiple above ~90 RPM
  if (rpm <= 90) return rpm
  return rpm / Math.ceil(rpm / 90)
}

function TopDrive({ twin }: { twin: TwinStateMsg | null }) {
  const ref = useRef<THREE.Group>(null)
  const angle = useRef(0)
  useFrame((_, dt) => {
    if (!ref.current || !twin) return
    const omega = (visualRpm(twin.rpm_surface) * Math.PI) / 30
    angle.current += omega * dt
    ref.current.rotation.y = angle.current
    ref.current.position.y = 8 + Math.min(4, twin.block_pos_m * 0.05)
  })
  return (
    <group ref={ref} position={[0, 8, 0]}>
      <mesh castShadow>
        <cylinderGeometry args={[0.45, 0.55, 1.2, 16]} />
        <meshStandardMaterial color="#8a9690" metalness={0.7} roughness={0.35} />
      </mesh>
      <mesh position={[0, 0.9, 0]}>
        <boxGeometry args={[1.4, 0.35, 1.4]} />
        <meshStandardMaterial color="#6c7872" metalness={0.6} roughness={0.4} />
      </mesh>
    </group>
  )
}

function Drillstring({ twin }: { twin: TwinStateMsg | null }) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const matRef = useRef<THREE.MeshStandardMaterial>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const surfAngle = useRef(0)
  const dhAngle = useRef(0)

  const dets = twin?.active_detections ?? []
  const stick = dets.find((d) => d.class === 'STICK_SLIP' && d.tier === 2)
  const whirl = twin?.whirl
  const bounce = twin?.bounce
  const tier1Amber = dets.some((d) => d.tier === 1) && !dets.some((d) => d.tier === 2)

  useFrame((_, dt) => {
    if (!meshRef.current || !twin) return
    const rpmS = visualRpm(twin.rpm_surface)
    const rpmD = visualRpm(twin.rpm_downhole)
    surfAngle.current += ((rpmS * Math.PI) / 30) * dt
    dhAngle.current += ((rpmD * Math.PI) / 30) * dt

    const twist = twin.twist_rad
    for (let i = 0; i < N_JOINTS; i++) {
      const u = i / (N_JOINTS - 1)
      let y: number
      if (u < 0.2) y = 7.2 - u * 8
      else if (u > 0.8) y = -4 - (u - 0.8) * 20
      else y = 7.2 - 1.6 - ((u - 0.2) / 0.6) * 9.6

      const twistFrac = stick ? u : u * 0.15
      const rot = surfAngle.current * (1 - u) + dhAngle.current * u + twist * twistFrac

      let x = 0
      let z = 0
      if (whirl?.active) {
        const ecc = whirl.eccentricity * 0.35 * (u > 0.75 ? (u - 0.75) / 0.25 : 0)
        x = Math.cos(whirl.phase_rad) * ecc
        z = Math.sin(whirl.phase_rad) * ecc
      }
      let yOff = 0
      if (bounce?.active && u > 0.85) {
        yOff = Math.sin(bounce.phase_rad) * (bounce.amp_mm / 1000) * 8
      }

      dummy.position.set(x, y + yOff, z)
      dummy.rotation.set(0, rot, 0)
      const isCollar = u > 0.85
      dummy.scale.set(isCollar ? 1.35 : 1, 1, isCollar ? 1.35 : 1)
      dummy.updateMatrix()
      meshRef.current.setMatrixAt(i, dummy.matrix)
    }
    meshRef.current.instanceMatrix.needsUpdate = true

    if (matRef.current) {
      if (stick) {
        matRef.current.emissive.set('#e6322a')
        matRef.current.emissiveIntensity = 0.35 + 0.5 * (stick.sssi ?? 0.3)
      } else if (tier1Amber) {
        matRef.current.emissive.set('#e8a317')
        matRef.current.emissiveIntensity = 0.25
      } else {
        matRef.current.emissive.set('#000000')
        matRef.current.emissiveIntensity = 0
      }
    }
  })

  return (
    <group>
      <instancedMesh ref={meshRef} args={[undefined, undefined, N_JOINTS]} castShadow>
        <cylinderGeometry
          args={[0.08 * Math.sqrt(RADIAL_X / 10), 0.08 * Math.sqrt(RADIAL_X / 10), 0.55, 8]}
        />
        <meshStandardMaterial
          ref={matRef}
          color="#9aa4a0"
          metalness={0.75}
          roughness={0.32}
          emissive="#000000"
          toneMapped={false}
        />
      </instancedMesh>
      <mesh position={[0.55, 1.2, 0]}>
        <boxGeometry args={[0.15, 0.02, 0.02]} />
        <meshBasicMaterial color="#e8a317" />
      </mesh>
      <mesh position={[0.55, -2.2, 0]}>
        <boxGeometry args={[0.15, 0.02, 0.02]} />
        <meshBasicMaterial color="#e8a317" />
      </mesh>
    </group>
  )
}

function Bit({ twin }: { twin: TwinStateMsg | null }) {
  const ref = useRef<THREE.Group>(null)
  const nBlades = 5
  useFrame(() => {
    if (!ref.current || !twin) return
    ref.current.rotation.y = twin.whirl.active ? twin.whirl.phase_rad / nBlades : 0
    const bounceY = twin.bounce.active
      ? Math.sin(twin.bounce.phase_rad) * (twin.bounce.amp_mm / 1000) * 6
      : 0
    let x = 0
    let z = 0
    if (twin.whirl.active) {
      const ecc = twin.whirl.eccentricity * 0.4
      x = Math.cos(twin.whirl.phase_rad) * ecc
      z = Math.sin(twin.whirl.phase_rad) * ecc
    }
    ref.current.position.set(x, -8.2 + bounceY, z)
  })

  const blades = useMemo(
    () =>
      Array.from({ length: nBlades }, (_, i) => {
        const a = (i / nBlades) * Math.PI * 2
        return (
          <mesh key={i} rotation={[0.4, a, 0]} position={[Math.cos(a) * 0.12, -0.1, Math.sin(a) * 0.12]}>
            <boxGeometry args={[0.06, 0.22, 0.03]} />
            <meshStandardMaterial color="#c5ccc8" metalness={0.8} roughness={0.25} />
          </mesh>
        )
      }),
    [],
  )

  // Whirl orbit trail
  const trailPts = useMemo(() => {
    const pts: [number, number, number][] = []
    for (let i = 0; i <= 64; i++) {
      const a = (i / 64) * Math.PI * 2
      pts.push([Math.cos(a) * 0.35, -8.2, Math.sin(a) * 0.35])
    }
    return pts
  }, [])

  return (
    <group>
      <group ref={ref} position={[0, -8.2, 0]}>
        <mesh>
          <cylinderGeometry args={[0.18, 0.22, 0.35, 12]} />
          <meshStandardMaterial color="#b0b8b3" metalness={0.7} roughness={0.3} />
        </mesh>
        {blades}
      </group>
      {twin?.whirl.active && (
        <Line points={trailPts} color="#e6322a" lineWidth={1.5} transparent opacity={0.55} />
      )}
    </group>
  )
}

function EarthSection() {
  return (
    <group>
      <mesh position={[0, -3, -1.2]} rotation={[0, 0, 0]}>
        <boxGeometry args={[6, 14, 2]} />
        <meshStandardMaterial color="#2a231c" roughness={1} />
      </mesh>
      {/* formation strata */}
      {[
        ['#3a3228', 2.5],
        ['#4a3f32', 0.5],
        ['#2f3a32', -1.5],
        ['#45382c', -3.5],
        ['#2c3330', -5.5],
      ].map(([c, y], i) => (
        <mesh key={i} position={[-1.6, y as number, -0.2]}>
          <boxGeometry args={[2.2, 1.8, 0.3]} />
          <meshStandardMaterial color={c as string} roughness={0.95} />
        </mesh>
      ))}
      {/* borehole tube (radial exaggerated) */}
      <mesh position={[0, -3, 0]} rotation={[0, 0, 0]}>
        <cylinderGeometry args={[0.55, 0.55, 14, 24, 1, true]} />
        <meshStandardMaterial
          color="#1a2822"
          side={THREE.BackSide}
          roughness={0.9}
          metalness={0.05}
        />
      </mesh>
      {/* mud annulus hint */}
      <mesh position={[0, -3, 0]}>
        <cylinderGeometry args={[0.42, 0.42, 13.5, 16, 1, true]} />
        <meshStandardMaterial color="#0d3a2a" transparent opacity={0.35} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

function RigFloor() {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 7.3, 0]} receiveShadow>
        <circleGeometry args={[3.2, 32]} />
        <meshStandardMaterial color="#1c2621" roughness={0.85} />
      </mesh>
      <mesh position={[0, 7.35, 0]}>
        <torusGeometry args={[1.1, 0.08, 8, 32]} />
        <meshStandardMaterial color="#5a6560" metalness={0.5} roughness={0.45} />
      </mesh>
      {/* derrick legs */}
      {[-1, 1].map((sx) =>
        [-1, 1].map((sz) => (
          <mesh key={`${sx}${sz}`} position={[sx * 1.6, 10.5, sz * 1.6]}>
            <boxGeometry args={[0.12, 6.5, 0.12]} />
            <meshStandardMaterial color="#6d7872" metalness={0.55} roughness={0.4} />
          </mesh>
        )),
      )}
    </group>
  )
}

function Scene() {
  const twin = useStreamStore((s) => s.twin)
  return (
    <>
      <color attach="background" args={['#070d0b']} />
      <fog attach="fog" args={['#070d0b', 12, 32]} />
      <ambientLight intensity={0.25} />
      <directionalLight
        castShadow
        intensity={1.1}
        position={[6, 14, 4]}
        shadow-mapSize={[1024, 1024]}
      />
      <pointLight intensity={0.4} position={[-3, 6, 2]} color="#4dff88" />
      <RigFloor />
      <EarthSection />
      <TopDrive twin={twin} />
      <Drillstring twin={twin} />
      <Bit twin={twin} />
      <OrbitControls
        enablePan
        maxPolarAngle={Math.PI * 0.92}
        minDistance={4}
        maxDistance={28}
        target={[0, -1, 0]}
      />
      <AdaptiveDpr pixelated />
    </>
  )
}

export function RigTwin() {
  const twin = useStreamStore((s) => s.twin)
  const hasTier2 = twin?.active_detections.some((d) => d.tier === 2)
  return (
    <div className="panel twin">
      <div className="panel-title">
        3D Rig · reconstructed from measured spectra
        <span style={{ float: 'right' }} className={hasTier2 ? 'tier-2' : 'num'}>
          {hasTier2 ? 'CHOREOGRAPHY' : 'IDLE'}
        </span>
      </div>
      <div className="twin-body">
        <Canvas shadows camera={{ position: [7, 2, 10], fov: 40 }} dpr={[1, 1.75]}>
          <Scene />
        </Canvas>
      </div>
      <style>{`
        .twin { display:flex; flex-direction:column; min-height:0; height:100%; }
        .twin-body { flex:1; min-height:0; background:#070d0b; }
      `}</style>
    </div>
  )
}
