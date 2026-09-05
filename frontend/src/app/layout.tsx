import type { Metadata } from "next";
import "./globals.css";
import "./fonts.css";
export const metadata: Metadata = {
  title: {
    default: "TerraLens — увидеть состояние поля",
    template: "%s · TerraLens",
  },
  description:
    "Спутниковая история полей, восстановление NDVI и объяснимые аномалии.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" className="dark">
      <head>
        <link
          rel="preload"
          href="/fonts/golos-text-cyrillic-wght-normal.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <link
          rel="preload"
          href="/fonts/golos-text-latin-wght-normal.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
      </head>
      <body>
        <a
          className="fixed -top-20 left-4 z-[100] rounded-md bg-primary px-4 py-3 text-primary-foreground focus:top-3"
          href="#main"
        >
          К содержимому
        </a>
        {children}
      </body>
    </html>
  );
}
