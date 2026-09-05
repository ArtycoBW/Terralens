import type { Metadata } from "next";
import "./globals.css";
import "@fontsource-variable/golos-text";
import "@fontsource-variable/jetbrains-mono";
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
