import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

export { Root as Sheet, Trigger as SheetTrigger, Title as SheetTitle, Description as SheetDescription } from '@radix-ui/react-dialog'

export function SheetContent({ children }: { children: ReactNode }) {
  return <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/45" /><Dialog.Content className="fixed inset-x-0 bottom-0 z-50 max-h-[88dvh] overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl outline-none dark:bg-slate-950 md:inset-y-0 md:left-auto md:right-0 md:w-[min(35rem,92vw)] md:max-h-none md:rounded-none"><Dialog.Close aria-label="Close" className="absolute right-4 top-4 rounded-lg p-2 text-slate-500 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:hover:bg-slate-800"><X size={20} /></Dialog.Close>{children}</Dialog.Content></Dialog.Portal>
}
