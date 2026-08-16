import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FileUploadMock } from "../../../components/ui/FileUploadMock";
import { Text } from "../../../components/ui/Text";

type DataImportStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

export function DataImportStep({ onNext }: DataImportStepProps) {
  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Existing data import
        </Text>
        <Text variant="body" color="secondary">
          Bring your customer list or active quotes across from another tool.
        </Text>

        <FileUploadMock label="Upload customer CSV" fileName="customers.csv" />
        <FileUploadMock label="Upload active quotes" fileName="quotes.csv" />

        <Button title="Start fresh" variant="primary" onPress={() => onNext({ skipped: false, startFresh: true })} />
        <Button title="Skip for now" variant="outline" onPress={() => onNext({ skipped: true })} />
      </View>
    </ScrollView>
  );
}
