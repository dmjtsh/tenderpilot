const DIRECTION_COLORS = [
  { bg: "bg-gray-100", text: "text-gray-900", border: "border-gray-400", hover: "hover:bg-gray-100 hover:border-gray-400 hover:text-gray-900" },
]

function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

export function getDirectionColor(name: string) {
  return DIRECTION_COLORS[hashString(name) % DIRECTION_COLORS.length]
}
