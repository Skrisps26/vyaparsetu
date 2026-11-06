import * as TabsPrimitive from '@radix-ui/react-tabs'
import type { ComponentPropsWithoutRef } from 'react'
import { cn } from '../../lib/cn'
export const Tabs = TabsPrimitive.Root
export const TabsContent = TabsPrimitive.Content
export const TabsList = ({ className, ...props }: ComponentPropsWithoutRef<typeof TabsPrimitive.List>) => <TabsPrimitive.List className={cn('grid grid-cols-3 rounded-xl bg-slate-100 p-1 dark:bg-slate-800', className)} {...props} />
export const TabsTrigger = ({ className, ...props }: ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>) => <TabsPrimitive.Trigger className={cn('rounded-lg px-2 py-2 text-xs font-semibold text-slate-600 outline-none data-[state=active]:bg-white data-[state=active]:text-slate-950 data-[state=active]:shadow-sm focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-300 dark:data-[state=active]:bg-slate-950 dark:data-[state=active]:text-white', className)} {...props} />
