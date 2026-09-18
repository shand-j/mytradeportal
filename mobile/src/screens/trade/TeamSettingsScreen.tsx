import { useState } from "react";
import { ScrollView, View } from "react-native";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { SelectableChip } from "../../components/ui/SelectableChip";
import { Text } from "../../components/ui/Text";
import { inviteUser, useTeamUsers } from "../../api/users";
import { ApiError, NetworkError } from "../../lib/apiClient";

export type TeamSettingsScreenProps = {
  onClose: () => void;
};

const ROLE_OPTIONS = [
  { key: "engineer", label: "Engineer" },
  { key: "office_manager", label: "Office manager" },
  { key: "admin", label: "Admin" },
];

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  office_manager: "Office manager",
  engineer: "Engineer",
};

export function TeamSettingsScreen({ onClose }: TeamSettingsScreenProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { users, isLoading } = useTeamUsers();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("engineer");
  const [error, setError] = useState<string | null>(null);
  const [seatLimitHit, setSeatLimitHit] = useState(false);
  const [invitedEmail, setInvitedEmail] = useState<string | null>(null);

  const inviteMutation = useMutation({
    mutationFn: inviteUser,
    onSuccess: (user) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      setInvitedEmail(user.email);
      setFullName("");
      setEmail("");
      setRole("engineer");
    },
    onError: (err) => {
      if (err instanceof NetworkError) {
        setError("Can't reach the server. Check your connection and try again.");
      } else if (err instanceof ApiError && err.status === 403) {
        // Structured seat_limit_reached payload — detail doesn't survive
        // ApiError's string flattening, so show our own upgrade copy.
        setSeatLimitHit(true);
      } else if (err instanceof ApiError && err.status === 409) {
        setError("That email is already on your team.");
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Couldn't send the invite. Please try again.");
      }
    },
  });

  const sendInvite = () => {
    setError(null);
    setSeatLimitHit(false);
    setInvitedEmail(null);
    if (!fullName.trim()) {
      setError("Enter their full name.");
      return;
    }
    if (!email.trim() || !email.includes("@")) {
      setError("Enter a valid email address.");
      return;
    }
    inviteMutation.mutate({ fullName: fullName.trim(), email: email.trim(), role });
  };

  return (
    <Screen>
      <Header testID="team-back" title="Team" onBack={onClose} />
      <ScrollView className="flex-1" contentContainerClassName="gap-4 pb-4">
        <Text variant="body" color="secondary">
          Invite people to your business. Each plan includes a set number of users — pending
          invites count until they're accepted.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            People
          </Text>
          {isLoading ? (
            <Text variant="caption" color="secondary">
              Loading…
            </Text>
          ) : (
            users.map((user, index) => (
              <View
                key={user.id}
                className={`flex-row items-center justify-between py-2 ${
                  index !== users.length - 1 ? "border-b border-slate-200" : ""
                }`}
              >
                <View className="flex-1 pr-3">
                  <Text variant="body" weight="semibold">
                    {user.fullName}
                  </Text>
                  <Text variant="caption" color="secondary">
                    {user.email} · {ROLE_LABELS[user.role] ?? user.role}
                  </Text>
                </View>
                {user.invitePending ? (
                  <View className="rounded-full bg-amber-100 px-2 py-0.5">
                    <Text testID={`team-pending-${user.email}`} variant="caption" weight="semibold">
                      Invited
                    </Text>
                  </View>
                ) : null}
              </View>
            ))
          )}
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Invite a team member
          </Text>
          <FormField
            testID="team-invite-name"
            label="Full name"
            value={fullName}
            onChangeText={setFullName}
            placeholder="Sam Spark"
          />
          <FormField
            testID="team-invite-email"
            label="Email"
            value={email}
            onChangeText={setEmail}
            placeholder="sam@example.com"
            keyboardType="email-address"
            autoCapitalize="none"
          />
          <View className="gap-1">
            <Text variant="body" weight="semibold">
              Role
            </Text>
            <View className="flex-row flex-wrap gap-2">
              {ROLE_OPTIONS.map((option) => (
                <SelectableChip
                  key={option.key}
                  testID={`team-invite-role-${option.key}`}
                  label={option.label}
                  selected={role === option.key}
                  onPress={() => setRole(option.key)}
                />
              ))}
            </View>
          </View>
          {error ? (
            <Text testID="team-invite-error" variant="caption" color="warning">
              {error}
            </Text>
          ) : null}
          {seatLimitHit ? (
            <View className="gap-2">
              <Text testID="team-invite-seat-limit" variant="caption" color="warning">
                Your plan has no seats left. Upgrade to add more team members.
              </Text>
              <Button
                testID="team-invite-upgrade"
                title="See plans"
                variant="outline"
                size="sm"
                onPress={() => router.push("/(trade)/billing")}
              />
            </View>
          ) : null}
          {invitedEmail ? (
            <Text testID="team-invite-sent" variant="caption" color="secondary">
              Invite sent to {invitedEmail}. They'll get an email with a link to set their
              password.
            </Text>
          ) : null}
          <Button
            testID="team-invite-submit"
            title={inviteMutation.isPending ? "Sending invite…" : "Send invite"}
            disabled={inviteMutation.isPending}
            onPress={sendInvite}
          />
        </View>
      </ScrollView>
    </Screen>
  );
}
