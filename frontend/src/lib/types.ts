/** Monitor stream message contracts (§17 / A14). */

export type DetectionTier = 1 | 2

export interface ActiveDetection {
  class: string
  tier: DetectionTier
  confidence: number
  p_corr: number
  score: number
  sssi?: number
  episode?: string
  distinct_matched?: number
}

export interface TwinStateMsg {
  type: 'twin_state'
  t: number
  bit_depth_m: number
  hole_depth_m: number
  rpm_surface: number
  rpm_downhole: number
  torque_knm: number
  wob_kn: number
  hookload_kn: number
  twist_rad: number
  block_pos_m: number
  active_detections: ActiveDetection[]
  whirl: {
    active: boolean
    order: number | null
    phase_rad: number
    eccentricity: number
  }
  bounce: {
    active: boolean
    amp_mm: number
    phase_rad: number
  }
}

export interface SpectralFrameMsg {
  type: 'spectral_frame'
  t: number
  channel: string
  profile: string
  db_floor: number
  db_ceil: number
  data_b64: string
  n_bins: number
}

export interface ConstellationMsg {
  type: 'constellation'
  t: number
  channel: string
  profile: string
  domain: string
  peaks: { t: number; bin: number; mag_db: number }[]
}

export interface DetectionMsg {
  type: 'detection'
  t: number
  class: string
  tier: DetectionTier
  episode?: string
  confidence: number
  score: number
  distinct_matched?: number
  lambda?: number
  lambda_geom?: number
  p_corr: number
  p_geom_corr?: number | null
  delta_star?: number
  histogram?: Record<string, number>
  sssi?: number | null
  library_version?: string
  diag?: Record<string, unknown>
}

export interface ScenarioEventMsg {
  type: 'scenario_event'
  t: number
  kind?: string
  caption?: string
  camera?: string
  [key: string]: unknown
}

export type MonitorMessage =
  | TwinStateMsg
  | SpectralFrameMsg
  | ConstellationMsg
  | DetectionMsg
  | ScenarioEventMsg

export interface ChannelBadge {
  channel: string
  fs?: number
  observes: string[]
  badge: string | null
  entirely_blind?: boolean
}

export interface LibraryInfo {
  version: string
  created: string
  notes: string
  status: string
  approved_by: string | null
  approved_at: string | null
  active: boolean
  episodes_by_class?: Record<string, number>
  n_hashes?: number
}
