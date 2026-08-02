import Image from 'next/image';
import Layout from '../components/Layout';

export default function Home() {
  return (
    <Layout>
      <div className="text-center">
        {/* El logo de la marca es blanco sobre transparente (el mismo del
            sidebar y del footer de la landing): va sobre una placa Deep Forest
            para que se lea, porque la tarjeta del Layout es blanca. */}
        <div className="inline-flex items-center justify-center bg-gloma-brown rounded-3xl px-10 py-6 mb-6">
          <Image
            src="/gloma/logo_blancotrans.png"
            alt="Gloma"
            width={462}
            height={541}
            priority
            className="object-contain h-24 w-auto"
          />
        </div>
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
