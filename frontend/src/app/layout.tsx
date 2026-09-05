import type { Metadata } from "next";
import "./globals.css";
import "@fontsource-variable/inter";
export const metadata: Metadata = { title: {default:"TerraLens — увидеть состояние поля", template:"%s · TerraLens"}, description:"Спутниковая история полей, восстановление NDVI и объяснимые аномалии." };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="ru"><body><a className="skip-link" href="#main">К содержимому</a>{children}</body></html>; }
