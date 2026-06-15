// color + label per event type (Tailwind hex used inline for the timeline)
export const EVENT_META = {
  hand_hygiene:       { color: '#16a34a', label: 'Ve sinh tay' },
  glove_on:           { color: '#0ea5e9', label: 'Mang gang' },
  glove_off:          { color: '#f97316', label: 'Thao gang' },
  touch_patient:      { color: '#a855f7', label: 'Cham BN' },
  touch_surroundings: { color: '#eab308', label: 'Cham moi truong' },
  aseptic_procedure:  { color: '#ec4899', label: 'Thu thuat vo trung' },
  body_fluid_exposure:{ color: '#dc2626', label: 'Nguy co dich co the' },
}

export const MOMENT_LABEL = {
  M1: 'M1 - Truoc khi cham BN',
  M2: 'M2 - Truoc thu thuat vo trung',
  M3: 'M3 - Sau nguy co dich co the',
  M4: 'M4 - Sau khi cham BN',
  M5: 'M5 - Sau khi cham moi truong',
}

export const SEVERITY_META = {
  high:   { color: 'bg-red-100 text-red-700 border-red-300', label: 'CAO' },
  medium: { color: 'bg-amber-100 text-amber-700 border-amber-300', label: 'TRUNG BINH' },
  low:    { color: 'bg-yellow-50 text-yellow-700 border-yellow-200', label: 'THAP' },
}
