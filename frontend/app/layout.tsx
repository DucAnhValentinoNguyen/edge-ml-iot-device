import "./globals.css";

export const metadata = {
  title: "EdgeLoop | Device Intelligence",
  description: "Deploy small, verifiable ML models into sensor devices.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

