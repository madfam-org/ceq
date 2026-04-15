"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

const Slider = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & {
    defaultValue?: number[]
    value?: number[]
    onValueChange?: (value: number[]) => void
    max?: number
    min?: number
    step?: number
  }
>(({ className, defaultValue, value, onValueChange, max = 100, min = 0, step = 1, ...props }, ref) => {
  const currentValue = value?.[0] ?? defaultValue?.[0] ?? min

  return (
    <input
      type="range"
      ref={ref}
      min={min}
      max={max}
      step={step}
      value={currentValue}
      onChange={(e) => onValueChange?.([Number(e.target.value)])}
      className={cn(
        "w-full h-2 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary",
        className
      )}
      {...props}
    />
  )
})
Slider.displayName = "Slider"

export { Slider }
