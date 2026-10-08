import { Modal, Pressable, Share, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { fetchCurrentTenant } from "../../api/businesses";
import { Button } from "../ui/Button";
import { QrCode } from "../ui/QrCode";
import { Text } from "../ui/Text";
import { useBusiness } from "../../theme/ThemeProvider";

export type PortalQrSheetProps = {
  visible: boolean;
  onClose: () => void;
};

/**
 * Bottom-sheet with the tenant's customer-portal QR code + share link.
 * Used from the quotes screen and settings so the "put this on your van"
 * affordance lives in both places.
 */
export function PortalQrSheet({ visible, onClose }: PortalQrSheetProps) {
  const { business } = useBusiness();
  // Trade login already loads the tenant into the business store; the query is
  // the same cache key the settings screens use, so this is usually free.
  const tenantQuery = useQuery({ queryKey: ["current-tenant"], queryFn: fetchCurrentTenant });
  const tenantSlug = tenantQuery.data?.slug ?? business?.slug ?? null;
  const portalUrl = tenantSlug ? `https://${tenantSlug}.mytradeportal.co.uk` : null;

  const sharePortalLink = () => {
    if (!portalUrl) return;
    void Share.share({
      message: `Get a quote from ${tenantQuery.data?.name ?? business?.name ?? "us"}: ${portalUrl}`,
    });
  };

  return (
    <Modal
      testID="qr-modal"
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable className="flex-1 justify-end bg-black/40" onPress={onClose}>
        <Pressable className="rounded-t-3xl bg-white px-6 pt-6 pb-10 gap-4" onPress={() => {}}>
          <Text variant="title" weight="bold" align="center">
            Your customer portal
          </Text>
          <Text variant="caption" color="secondary" align="center">
            Customers scan this to request a quote — print it for your van, invoices, or business cards.
          </Text>
          {portalUrl ? (
            <View className="items-center py-2">
              <QrCode testID="portal-qr-code" value={portalUrl} size={200} />
            </View>
          ) : (
            <Text variant="body" color="secondary" align="center">
              Your portal link is still loading — pull to retry in a moment.
            </Text>
          )}
          {portalUrl && (
            <Text testID="portal-url" variant="body" weight="semibold" align="center">
              {portalUrl}
            </Text>
          )}
          <Button
            testID="qr-share-link"
            title="Share link"
            disabled={!portalUrl}
            onPress={sharePortalLink}
          />
          <Button title="Close" variant="outline" onPress={onClose} />
        </Pressable>
      </Pressable>
    </Modal>
  );
}
