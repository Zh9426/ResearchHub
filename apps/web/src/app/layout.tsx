import type {Metadata,Viewport} from 'next';
import './globals.css';
export const metadata:Metadata={title:'Research Hub',description:'个人科研工作系统',manifest:'/manifest.webmanifest',appleWebApp:{capable:true,statusBarStyle:'default',title:'Research Hub'},icons:{icon:'/icons/icon.svg',apple:'/icons/icon-192.png'}};
export const viewport:Viewport={width:'device-width',initialScale:1,viewportFit:'cover',themeColor:'#116b66'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="zh-CN"><body>{children}</body></html>}
