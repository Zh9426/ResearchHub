'use client';
import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
export function useData<T>(path:string|null) {
  const [data,setData]=useState<T|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[version,setVersion]=useState(0);
  const refresh=useCallback(()=>setVersion(x=>x+1),[]);
  useEffect(()=>{let active=true;setError('');setLoading(true);setData(null);if(!path){setLoading(false);return;}api<T>(path).then(x=>{if(active)setData(x);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[path,version]);
  return {data,error,loading,refresh};
}
