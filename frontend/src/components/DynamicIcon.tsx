import React from "react"
import * as Icons from "lucide-react"

interface DynamicIconProps extends React.SVGProps<SVGSVGElement> {
  name: string
  className?: string
  size?: number
}

export const DynamicIcon: React.FC<DynamicIconProps> = ({ name, className = "w-4 h-4", size = 18, ...props }) => {
  // @ts-expect-error dynamic indexing into Lucide icons
  const IconComponent = Icons[name] || Icons.CircleDot

  return <IconComponent className={className} size={size} {...props} />
}
