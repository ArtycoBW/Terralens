import { FieldDetail } from "@/components/fields/field-detail";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <FieldDetail id={id} />;
}
