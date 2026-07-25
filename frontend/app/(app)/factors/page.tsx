import { redirect } from 'next/navigation'

export default function LegacyCapabilityRedirectPage() {
  redirect('/plugins?tab=capabilities')
}
