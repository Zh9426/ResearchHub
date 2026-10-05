import {Suspense} from 'react';
import {Hub} from '@/components/hub';
export default function Page(){return <Suspense fallback={<p>正在加载…</p>}><Hub/></Suspense>}
