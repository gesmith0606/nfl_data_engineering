"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { searchPlayers } from "@/lib/api";
import type { PlayerSearchResult } from "@/lib/types";

const POSITION_COLORS: Record<string, string> = {
  QB: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  RB: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  WR: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  TE: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  K: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

export default function SearchBar() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerSearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const data = await searchPlayers(query);
        setResults(data);
        setIsOpen(true);
      } catch {
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative w-full max-w-xs">
      <input
        type="text"
        placeholder="Search players..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder-gray-400"
      />
      {isLoading && (
        <div className="absolute right-3 top-2.5">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
        </div>
      )}
      {isOpen && results.length > 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
          {results.slice(0, 8).map((player) => (
            <button
              key={player.player_id}
              onClick={() => {
                router.push(`/players/${player.player_id}`);
                setIsOpen(false);
                setQuery("");
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <span
                className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${POSITION_COLORS[player.position] || "bg-gray-100 text-gray-700"}`}
              >
                {player.position}
              </span>
              <span className="text-gray-900 dark:text-white">
                {player.player_name}
              </span>
              <span className="ml-auto text-xs text-gray-500">
                {player.team}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
