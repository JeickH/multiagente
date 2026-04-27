import Image from 'next/image';
import Layout from '../components/Layout';

export default function Home() {
  return (
    <Layout>
      <div className="text-center">
        <Image
          src="/gloma/logo_gloma_original_trans.png"
          alt="Gloma"
          width={320}
          height={400}
          priority
          className="object-contain h-28 w-auto mx-auto mb-4"
        />
        <h1 className="font-heading text-3xl font-semibold text-gloma-brown mb-2">
          Bienvenida a Gloma
        </h1>
        <p className="text-gloma-brown-light">
          Tu plataforma de gestión de WhatsApp Business
        </p>
      </div>
    </Layout>
  );
}
