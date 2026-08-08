import { useCallback, useEffect, useRef, useState } from 'react'

const CHANNEL_NAME = 'kapexai-tab-lock'
const STORAGE_KEY = 'kapexai-tab-lock'
const HEARTBEAT_MS = 1500
const STALE_MS = 6000

type LockRecord = { tabId: string; ts: number }

/**
 * Enforces a single active chat tab per browser via a localStorage heartbeat +
 * BroadcastChannel. A second tab detects the first one and shows a blocked
 * state; the user can take over ("use this tab instead"), which blocks the
 * other tab. When the active tab is closed, a blocked tab auto-reclaims after
 * the heartbeat goes stale.
 */
export function useSingleTab(): { blocked: boolean; claimTab: () => void } {
  const tabIdRef = useRef<string>(crypto.randomUUID())
  const [blocked, setBlocked] = useState(false)
  const channelRef = useRef<BroadcastChannel | null>(null)
  const activeRef = useRef(true)

  const writeHeartbeat = useCallback(() => {
    const record: LockRecord = { tabId: tabIdRef.current, ts: Date.now() }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record))
  }, [])

  const readLock = useCallback((): LockRecord | null => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      return raw ? (JSON.parse(raw) as LockRecord) : null
    } catch {
      return null
    }
  }, [])

  const heldByOtherTab = useCallback(
    (now: number = Date.now()): boolean => {
      const lock = readLock()
      return Boolean(
        lock && lock.tabId !== tabIdRef.current && now - lock.ts < STALE_MS,
      )
    },
    [readLock],
  )

  const claimTab = useCallback(() => {
    activeRef.current = true
    setBlocked(false)
    writeHeartbeat()
    channelRef.current?.postMessage({ type: 'claim', tabId: tabIdRef.current })
  }, [writeHeartbeat])

  useEffect(() => {
    const tabId = tabIdRef.current
    const channel = new BroadcastChannel(CHANNEL_NAME)
    channelRef.current = channel

    channel.onmessage = (event: MessageEvent) => {
      const data = event.data as { type?: string; tabId?: string } | null
      if (!data || data.tabId === tabId || data.type !== 'claim') return
      // Another tab took over the lock.
      activeRef.current = false
      setBlocked(true)
    }

    // Immediately register ourselves, then re-check after a short grace period
    // so two tabs opened at the same time settle on exactly one active tab.
    writeHeartbeat()
    const settleTimer = setTimeout(() => {
      if (heldByOtherTab()) {
        activeRef.current = false
        setBlocked(true)
      } else {
        channel.postMessage({ type: 'claim', tabId })
      }
    }, 300)

    const heartbeat = setInterval(() => {
      if (activeRef.current) {
        writeHeartbeat()
      } else if (!heldByOtherTab()) {
        // The previous holder went away — take over.
        claimTab()
      }
    }, HEARTBEAT_MS)

    const onVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return
      if (heldByOtherTab()) {
        activeRef.current = false
        setBlocked(true)
      } else {
        claimTab()
      }
    }
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      clearTimeout(settleTimer)
      clearInterval(heartbeat)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      channel.close()
      channelRef.current = null
    }
  }, [claimTab, heldByOtherTab, writeHeartbeat])

  return { blocked, claimTab }
}
