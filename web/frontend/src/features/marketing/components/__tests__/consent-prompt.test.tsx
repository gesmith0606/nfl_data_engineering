import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useUser } from "@clerk/nextjs";
import { ConsentPrompt } from "../consent-prompt";

vi.mock("@clerk/nextjs", () => ({
  useUser: vi.fn(),
}));

const mockUseUser = vi.mocked(useUser);

function mockUser(publicMetadata: Record<string, unknown> = {}, reload = vi.fn()) {
  return { publicMetadata, reload } as never;
}

describe("ConsentPrompt", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  });

  it("renders nothing while Clerk is still loading", () => {
    mockUseUser.mockReturnValue({ isLoaded: false, isSignedIn: false, user: null } as never);
    const { container } = render(<ConsentPrompt />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when signed out", () => {
    mockUseUser.mockReturnValue({ isLoaded: true, isSignedIn: false, user: null } as never);
    const { container } = render(<ConsentPrompt />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing once the user already has a recorded consent choice", () => {
    mockUseUser.mockReturnValue({
      isLoaded: true,
      isSignedIn: true,
      user: mockUser({ marketingConsent: false }),
    } as never);
    const { container } = render(<ConsentPrompt />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the prompt, unchecked by default, for a signed-in user with no consent stamp", () => {
    mockUseUser.mockReturnValue({
      isLoaded: true,
      isSignedIn: true,
      user: mockUser(),
    } as never);
    render(<ConsentPrompt />);
    const checkbox = screen.getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    expect(
      screen.getByText("Send me product updates & fantasy insights (optional)"),
    ).toBeInTheDocument();
  });

  it("posts consent:true and hides after checking the box and saving", async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    mockUseUser.mockReturnValue({
      isLoaded: true,
      isSignedIn: true,
      user: mockUser({}, reload),
    } as never);
    render(<ConsentPrompt />);

    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/marketing/consent",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ consent: true }),
        }),
      ),
    );
    await waitFor(() => expect(screen.queryByRole("checkbox")).not.toBeInTheDocument());
    expect(reload).toHaveBeenCalled();
  });

  it("posts consent:false and hides when dismissed without checking", async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    mockUseUser.mockReturnValue({
      isLoaded: true,
      isSignedIn: true,
      user: mockUser({}, reload),
    } as never);
    render(<ConsentPrompt />);

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/marketing/consent",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ consent: false }),
        }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument(),
    );
  });
});
