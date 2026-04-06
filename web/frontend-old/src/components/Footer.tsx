export default function Footer() {
  return (
    <footer className="mt-auto border-t border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Powered by{" "}
            <span className="font-semibold text-gray-700 dark:text-gray-300">
              NFL Data Engineering
            </span>
          </p>
          <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
            <a
              href="https://github.com/gesmith0606/nfl_data_engineering"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-colors hover:text-gray-700 dark:hover:text-gray-300"
            >
              GitHub
            </a>
            <span className="text-gray-300 dark:text-gray-600">|</span>
            <a
              href="/api/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-colors hover:text-gray-700 dark:hover:text-gray-300"
            >
              API Docs
            </a>
            <span className="text-gray-300 dark:text-gray-600">|</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              v0.1.0
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
