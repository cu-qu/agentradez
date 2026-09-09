import type { ReactNode } from "react";
import type { Metadata } from "next";
import Link from "next/link";

import { MarketingShell } from "@/components/marketing-shell";

export const metadata: Metadata = {
  title: "Terms and Conditions",
  description:
    "Terms and Conditions for Agentradez, including risk disclosures and limitation of liability.",
};

const updated = "August 21, 2026";

export default function TermsPage() {
  return (
    <MarketingShell>
      <div className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        Terms and Conditions
      </h1>
      <p className="mt-2 text-sm text-muted">Last updated {updated}</p>

      <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-foreground/90">
        <p>
          These Terms and Conditions (“Terms”) govern your access to and use of
          Agentradez, including the website, software, automation, signals,
          copy-trading features, and related services (the “Service”). The
          Service is operated by the host and operator of Agentradez (“we,”
          “us,” or “our”). By creating an account, checking the agreement box,
          or using the Service, you agree to these Terms. If you do not agree,
          do not use the Service.
        </p>

        <Section title="1. Nature of the Service">
          <p>
            Agentradez is a software platform that may help you connect a
            brokerage account, view information, and place or automate orders
            through third-party brokers. We are a technology provider only.
          </p>
          <p>
            We are not a bank, broker-dealer, futures commission merchant,
            introducing broker, commodity trading advisor, investment adviser,
            fiduciary, or financial planner. We are not registered with the
            U.S. Securities and Exchange Commission (SEC), FINRA, the CFTC,
            NFA, or any comparable regulator as a broker or adviser. Nothing on
            the Service is an offer to buy or sell any security or other
            financial instrument.
          </p>
        </Section>

        <Section title="2. Not financial advice">
          <p>
            All content, strategies, signals, copy-trade sources, risk tiers,
            analytics, notifications, model outputs, and automation on the
            Service are for informational and educational purposes only. They
            are not financial, investment, trading, tax, accounting, or legal
            advice. We do not recommend any particular security, option,
            strategy, or course of action.
          </p>
          <p>
            You alone decide whether to connect an account, enable automation,
            follow a signal, or place, modify, or cancel any order. You should
            consult a licensed professional if you need advice. You should not
            construe any feature of the Service as a solicitation or a
            personalized recommendation tailored to your circumstances.
          </p>
        </Section>

        <Section title="3. Risk of loss; we are not responsible for losses">
          <p>
            Trading securities and options involves a high risk of loss and is
            not suitable for everyone. You can lose some or all of the capital
            you trade. Options can expire worthless. Automated and copy trading
            can multiply losses, place unwanted orders, or fail to place wanted
            orders. Past performance, backtests, and other people’s results do
            not predict future results.
          </p>
          <p>
            To the maximum extent permitted by law, we are not responsible for
            any trading losses, missed trades, slippage, failed or delayed
            orders, liquidations, assignment, exercise, margin calls, taxes, or
            other financial harm arising from your use of the Service, from
            signals or automation, from bugs or downtime, or from your
            brokerage account. You use the Service at your sole risk and you
            remain solely responsible for all activity in your connected
            accounts.
          </p>
        </Section>

        <Section title="4. Automated, agentic, and copy trading">
          <p>
            If you enable automation, copy trading, or similar features, you
            authorize the Service to generate and submit instructions to your
            broker on your behalf, including buy, sell, cancel, and related
            orders, according to the settings you choose. Software, models, and
            agents can be wrong, delayed, incomplete, or unavailable. They may
            misread signals, size positions incorrectly, trade more or less
            often than you expect, or continue trading after you intended to
            stop.
          </p>
          <p>
            You are responsible for monitoring your account, positions, buying
            power, and open orders. We have no duty to supervise your trading,
            to stop losses, to confirm that a trade is appropriate for you, or
            to notify you of every action taken or not taken.
          </p>
        </Section>

        <Section title="5. Brokers, market data, and third parties">
          <p>
            Order execution, custody, margin, account approval, and
            confirmations are handled by your broker, not by us. Your
            relationship with any broker is governed by that broker’s
            agreements. We do not control market hours, quotes, fills,
            routing, halts, corporate actions, or broker outages.
          </p>
          <p>
            Market data, social or signal sources, and other third-party
            information may be delayed, inaccurate, or interrupted. We are not
            liable for those sources or for your broker’s acts or omissions.
            You must comply with your broker’s terms and applicable exchange
            and market rules.
          </p>
        </Section>

        <Section title="6. Eligibility and your account">
          <p>
            You must be at least 18 years old (or the age of majority where
            you live, if higher) and legally able to enter this contract. You
            represent that you are not barred from using the Service under
            applicable law, including sanctions and securities laws, and that
            you have full authority to connect any brokerage account you link.
          </p>
          <p>
            You are responsible for keeping your credentials confidential and
            for all activity under your account. Notify us promptly if you
            believe your account was compromised. We may refuse, suspend, or
            close accounts at our discretion, including to protect the Service
            or to comply with law.
          </p>
        </Section>

        <Section title="7. Acceptable use">
          <p>You agree not to:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>use the Service for any unlawful purpose, including market manipulation, fraud, or trading with material nonpublic information;</li>
            <li>attempt to gain unauthorized access to the Service, other accounts, or related systems;</li>
            <li>probe, scan, disrupt, overload, or reverse engineer the Service except as allowed by law;</li>
            <li>interfere with other users or with our hosting, security, or operations;</li>
            <li>misrepresent your identity, age, or authority over a brokerage account;</li>
            <li>use the Service in a way that creates regulatory, legal, or reputational risk for us as the host.</li>
          </ul>
        </Section>

        <Section title="8. Intellectual property">
          <p>
            We and our licensors own the Service, including software, design,
            text, logos, and other content, excluding your own data and
            third-party materials. You receive a limited, revocable,
            non-exclusive, non-transferable license to use the Service for
            your personal, lawful purposes while these Terms remain in effect.
            You may not copy, scrape, resell, or create a competing service
            from our materials without our written permission.
          </p>
        </Section>

        <Section title="9. Marketing use of P&L and performance">
          <p>
            You grant us a worldwide, royalty-free, perpetual license to use,
            reproduce, display, and publish profit-and-loss (P&amp;L),
            performance, and related trading results from orders submitted
            through Agentradez on your connected brokerage accounts, for
            marketing, promotional, advertising, and educational purposes, both
            on the Service and outside the Service (including websites, social
            media, advertisements, case studies, and other materials).
          </p>
          <p>
            We may present this information in aggregated, anonymized, or
            example form. We will not publish your legal name, account numbers,
            or login credentials without your separate consent. Past results
            shown in marketing are not indicative of future results.
          </p>
        </Section>

        <Section title="10. Service availability and changes">
          <p>
            We provide the Service on an “as available” basis. We do not
            guarantee uptime, error-free operation, or that automation will
            run at any particular time. Hosting, networks, brokers, and
            dependencies can fail. We may modify, suspend, throttle, or
            discontinue any part of the Service at any time, with or without
            notice, including for maintenance, abuse, legal risk, or
            operational reasons.
          </p>
          <p>
            Features, strategies, signals, and risk settings can change or be
            removed. We are not obligated to continue any strategy, copy
            source, or integration.
          </p>
        </Section>

        <Section title="11. Disclaimer of warranties">
          <p>
            TO THE MAXIMUM EXTENT PERMITTED BY LAW, THE SERVICE IS PROVIDED
            “AS IS” AND “AS AVAILABLE,” WITHOUT WARRANTIES OF ANY KIND,
            WHETHER EXPRESS, IMPLIED, OR STATUTORY, INCLUDING IMPLIED
            WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE,
            TITLE, NON-INFRINGEMENT, AND ACCURACY. WE DO NOT WARRANT THAT THE
            SERVICE WILL MEET YOUR EXPECTATIONS, BE PROFITABLE, BE SECURE, OR
            OPERATE WITHOUT INTERRUPTION OR ERROR.
          </p>
        </Section>

        <Section title="12. Limitation of liability">
          <p>
            TO THE MAXIMUM EXTENT PERMITTED BY LAW, WE AND OUR OWNERS,
            OPERATORS, HOSTS, OFFICERS, EMPLOYEES, CONTRACTORS, AND LICENSORS
            WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL,
            CONSEQUENTIAL, EXEMPLARY, OR PUNITIVE DAMAGES, OR FOR ANY LOSS OF
            PROFITS, TRADING GAINS, DATA, GOODWILL, OR BUSINESS, EVEN IF
            ADVISED OF THE POSSIBILITY.
          </p>
          <p>
            OUR TOTAL LIABILITY FOR ANY CLAIM ARISING OUT OF THE SERVICE OR
            THESE TERMS WILL NOT EXCEED THE GREATER OF (A) THE AMOUNTS YOU
            PAID US FOR THE SERVICE IN THE TWELVE MONTHS BEFORE THE CLAIM OR
            (B) ONE HUNDRED U.S. DOLLARS (US $100). THESE LIMITS APPLY TO
            LOSSES FROM TRADING, AUTOMATION, DOWNTIME, BUGS, SECURITY
            INCIDENTS, AND THIRD-PARTY SERVICES, TO THE FULLEST EXTENT THE LAW
            ALLOWS.
          </p>
          <p>
            Some places do not allow certain limitations. In those places, our
            liability is limited to the greatest extent permitted.
          </p>
        </Section>

        <Section title="13. Indemnification">
          <p>
            You will defend, indemnify, and hold harmless us and our owners,
            operators, hosts, officers, employees, contractors, and licensors
            from any claim, loss, liability, damage, cost, or expense
            (including reasonable attorneys’ fees) arising out of: your use of
            the Service; your trading or connected accounts; your violation of
            these Terms or of law; your violation of a broker’s or third
            party’s rights or agreements; or content or instructions you
            provide. We may assume exclusive defense of any matter, at your
            expense, and you will cooperate.
          </p>
        </Section>

        <Section title="14. Taxes and compliance">
          <p>
            You are solely responsible for reporting and paying taxes on
            trading activity and for complying with securities, commodities,
            and other laws that apply to you. We do not provide tax documents
            unless required by law, and any figures shown in the Service are
            not official tax records.
          </p>
        </Section>

        <Section title="15. Termination">
          <p>
            You may stop using the Service at any time. We may suspend or
            terminate access immediately if we believe you breached these
            Terms, created risk for us or others, or if we discontinue the
            Service. Sections that by their nature should survive
            (including disclaimers, limitation of liability,
            indemnification, and marketing licenses) will survive
            termination. Termination does not cancel orders already
            submitted to your broker; you must manage those with your
            broker.
          </p>
        </Section>

        <Section title="16. Changes to these Terms">
          <p>
            We may update these Terms from time to time. The “Last updated”
            date will change when we do. Continued use after changes become
            effective constitutes acceptance. If you do not agree, you must
            stop using the Service and close your account.
          </p>
        </Section>

        <Section title="17. Governing law; disputes">
          <p>
            These Terms are governed by the laws of the jurisdiction in which
            the operator of the Service is established, without regard to
            conflict-of-law rules. To the extent permitted by law, you agree
            that courts in that jurisdiction are the exclusive venue for
            disputes, and you consent to personal jurisdiction there. We may
            seek injunctive or equivalent relief in any forum to protect the
            Service or our rights.
          </p>
          <p>
            You may only bring claims in your individual capacity, not as a
            plaintiff or class member in any class, collective, or
            representative action, to the extent such a waiver is permitted
            by law.
          </p>
        </Section>

        <Section title="18. Miscellaneous">
          <p>
            These Terms are the entire agreement between you and us regarding
            the Service and supersede prior understandings on that subject. If
            a provision is unenforceable, the rest remains in effect. Our
            failure to enforce a provision is not a waiver. You may not assign
            these Terms without our consent; we may assign them in connection
            with a reorganization, hosting change, or transfer of the
            Service. Headings are for convenience only. “Including” means
            “including without limitation.”
          </p>
          <p>
            Checking the box on sign-up, creating an account, or using the
            Service is your electronic signature and acknowledgment that you
            have read, understood, and agree to these Terms.
          </p>
        </Section>
      </div>

      <p className="mt-10 text-sm text-muted">
        <Link href="/" className="text-foreground hover:underline">
          Home
        </Link>
        <span className="mx-2">·</span>
        <Link href="/register" className="text-foreground hover:underline">
          Create account
        </Link>
        <span className="mx-2">·</span>
        <Link href="/login" className="text-foreground hover:underline">
          Sign in
        </Link>
      </p>
      </div>
    </MarketingShell>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xs font-medium uppercase tracking-wide text-muted">
        {title}
      </h2>
      {children}
    </section>
  );
}
