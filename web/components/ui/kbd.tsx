import * as React from 'react'

import { cn } from '@/lib/utils'

/** A key on the keyboard, for shortcut hints: <Kbd>⌘</Kbd> <Kbd>K</Kbd>. */
function Kbd({ className, ...props }: React.ComponentProps<'kbd'>) {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded border border-gray-200 bg-white px-1 font-mono text-[11px] text-muted-foreground dark:border-gray-800 dark:bg-black/50',
        className,
      )}
      {...props}
    />
  )
}

export { Kbd }
